"""
ノード関連のクラス
"""
from PySide6.QtCore import QPointF, Qt, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPen, QColor, QPainter, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsTextItem,
    QGraphicsItem,
)

import math

# 循環インポートを避けるため、型チェック時のみインポート
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from view import MindMapView
    from connection import CrankConnection


class NodeItem(QGraphicsRectItem):
    """
    マインドマップのノードを表現するクラス
    
    このクラスは以下の機能を提供します：
    - ドラッグ可能で選択可能なノードの表示
    - ノードのテキスト編集機能
    - ノード間の接続線（CrankConnection）の管理
    - ノードの移動時の接続線の自動更新
    - ノードの選択状態の管理
    - ノードのサイズと位置の管理
    
    主要なメソッド：
    - set_text(): ノードのテキスト設定
    - attach_edge(): 接続線の追加
    - detach_edge(): 接続線の削除
    - itemChange(): ノードの変更時の処理
    - mouseDoubleClickEvent(): ダブルクリック時のテキスト編集
    """
    
    def __init__(self, view: 'MindMapView', label: str = "ノード", width: float = 128.0, height: float = 72.0):
        super().__init__(-width/2, -height/2, width, height)
        self._view = view
        self._edges: list[tuple['CrankConnection', 'NodeItem']] = []
        self._press_pos: QPointF | None = None
        # 接続線の縦線重なり回避用のオフセット
        self.vertical_line_offset: float = 0.0
        
        # テキストエディターを初期化
        from text_editor import NodeTextEditor
        self.text_editor = NodeTextEditor(self)
        
        # ノードの設定
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # テキストアイテム
        self.text_item = QGraphicsTextItem(label, self)
        self.text_item.setDefaultTextColor(Qt.black)
        self._update_text_position()
        
        # 選択状態のスタイル
        self._update_selection_style()
        
    
    def attach_edge(self, connection: 'CrankConnection', other_node: 'NodeItem') -> None:
        """エッジを接続"""
        self._edges.append((connection, other_node))
        self._update_attached_lines()
    
    def detach_edge(self, connection: 'CrankConnection', other_node: 'NodeItem') -> None:
        """エッジを切断"""
        self._edges = [(c, n) for c, n in self._edges if c != connection or n != other_node]
    
    def _update_attached_lines(self) -> None:
        """接続された線を更新"""
        for connection, _ in self._edges:
            connection.update_connection()
    
    def _update_selection_style(self):
        """選択状態に応じて枠線のスタイルを更新"""
        if self.isSelected():
            self.setPen(QPen(Qt.gray, 1.6))
        else:
            self.setPen(QPen(QColor(200, 200, 200), 1.5))
    
    def _update_text_position(self):
        """テキストの位置を更新"""
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(-text_rect.width() / 2.0, -text_rect.height() / 2.0)
    
    def itemChange(self, change: 'QGraphicsItem.GraphicsItemChange', value):
        """アイテムの変更を処理"""
        # テキスト編集中は位置変更を無効化
        if change == QGraphicsItem.ItemPositionChange and self.text_editor.is_editing:
            return self.pos()
        
        if change == QGraphicsItem.ItemPositionChange:
            # サブツリードラッグ中の場合は制限を緩和（ただしグリッドスナップは適用）
            if self._view._subtree_drag_mode:
                if self._view.get_grid_snap_enabled():
                    return self._view.snap_to_grid(value)
                else:
                    return value
            
            # 複数ノード選択時の移動は制限を緩和
            selected_items = self._view.scene.selectedItems()
            if len(selected_items) > 1:
                # 複数ノード選択時はグリッドスナップのみ適用
                if self._view.get_grid_snap_enabled():
                    return self._view.snap_to_grid(value)
                else:
                    return value
            else:
                # 単一ノード選択時は従来の処理
                if self._view.get_grid_snap_enabled():
                    snapped_pos = self._view.snap_to_grid(value)
                    if self._view._is_position_free_for_node(snapped_pos, self):
                        return snapped_pos
                    else:
                        return self.pos()
                else:
                    if self._view._is_position_free_for_node(value, self):
                        return value
                    else:
                        return self.pos()
        
        # 位置変更後にライン更新とサブツリードラッグ処理
        if change == QGraphicsItem.ItemPositionHasChanged:
            # サブツリードラッグ中でない場合のみ通常のライン更新を行う
            if not self._view._subtree_drag_mode:
                self._update_attached_lines()
            
            # サブツリードラッグ中の場合は子孫ノードを移動
            if self._view._subtree_drag_mode and self == self._view._subtree_drag_root:
                current_pos = self.pos()
                if self._view._subtree_drag_start_pos is not None:
                    dx = current_pos.x() - self._view._subtree_drag_start_pos.x()
                    dy = current_pos.y() - self._view._subtree_drag_start_pos.y()
                    self._view.update_subtree_drag(dx, dy)
            
            # 複数ノード移動中の場合は接続線を更新
            if self._view._is_multi_move_in_progress:
                # このノードに関連する接続線を更新
                for connection in self._view.connections:
                    if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                        (connection.source == self or connection.target == self)):
                        if hasattr(connection, 'update_connection'):
                            connection.update_connection()
        # 選択状態の変化を検知して枠線の太さを調整
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self._update_selection_style()
        
        return super().itemChange(change, value)
    
    
    def mousePressEvent(self, event):
        """マウスプレスイベント"""
        # テキスト編集中はマウスイベントを無効化
        if self.text_editor.is_editing:
            return
        
        # Shiftキーが押されている場合はサブツリードラッグを開始しない（単独ノード移動）
        if event.button() == Qt.LeftButton:
            if not (event.modifiers() & Qt.ShiftModifier):
                # Shiftキーが押されていない場合のみサブツリードラッグを開始
                self._view.begin_subtree_drag(self)
        
        self._press_pos = self.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """マウス移動イベント"""
        # テキスト編集中はマウスイベントを無効化
        if self.text_editor.is_editing:
            return
        
        # ドラッグ中は自由に移動を許可（衝突チェックはmouseReleaseEventで行う）
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """マウスリリースイベント"""
        # テキスト編集中はマウスイベントを無効化
        if self.text_editor.is_editing:
            return
        
        # サブツリードラッグの終了は衝突判定後に行うため、ここではフラグだけ立てる
        should_end_subtree_drag = (event.button() == Qt.LeftButton and not (event.modifiers() & Qt.ShiftModifier))
        
        if self._press_pos is not None and self._press_pos != self.pos():
            # 複数ノード移動中は個別の処理をスキップ
            if self._view._is_multi_move_in_progress:
                self._press_pos = None
                return super().mouseReleaseEvent(event)
            
            # グリッドスナップがOFFの場合のみ手動でスナップを適用
            if not self._view.get_grid_snap_enabled():
                snapped_pos = self._view.snap_to_grid(self.pos())
                if snapped_pos != self.pos():
                    self.setPos(snapped_pos)
            
            # ノードの種類に関係なく「縦レーン」割り込みを適用
            lane_insert, lane_nodes, lane_index = self._view._check_lane_insertion(self, self.pos())
            if lane_insert:
                nodes_with_dragged = lane_nodes.copy()
                nodes_with_dragged.insert(lane_index, self)
                self._view._reposition_lane_nodes(nodes_with_dragged)
                if should_end_subtree_drag:
                    self._view.end_subtree_drag()
                self._press_pos = None
                return super().mouseReleaseEvent(event)
            
            # 衝突検出：単体ノード衝突 または サブツリー衝突
            subtree_collision = False
            if getattr(self._view, '_subtree_drag_mode', False) and self == getattr(self._view, '_subtree_drag_root', None):
                if hasattr(self._view, '_check_subtree_collision'):
                    subtree_collision = self._view._check_subtree_collision(self)
            if self._view._check_node_collision(self, self.pos()) or subtree_collision:
                # サブツリードラッグ中の場合は子孫ノードも元の位置に戻す
                if self._view._subtree_drag_mode and self == self._view._subtree_drag_root:
                    # 子孫ノードの位置を元に戻す
                    if hasattr(self._view, '_subtree_drag_original_positions'):
                        for node, original_pos in self._view._subtree_drag_original_positions.items():
                            if node != self:  # 自分以外の子孫ノード
                                node.setPos(original_pos)
                
                # 元の位置に戻す
                self.setPos(self._press_pos)
                # 接続線を更新
                for connection, other_node in self._edges:
                    connection.update_connection()
                # 他の接続線も更新
                for connection in self._view.connections:
                    if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                        (connection.source == self or connection.target == self)):
                        if hasattr(connection, 'update_connection'):
                            connection.update_connection()
                # 衝突復帰後に必要ならサブツリードラッグを終了
                if should_end_subtree_drag:
                    self._view.end_subtree_drag()
                return super().mouseReleaseEvent(event)
            
            # 移動距離が十分大きい場合のみUndoスタックに追加
            move_distance = ((self.pos().x() - self._press_pos.x()) ** 2 + 
                           (self.pos().y() - self._press_pos.y()) ** 2) ** 0.5
            
            if move_distance > 5.0 and self._view.undo_stack is not None:
                # 複数ノード移動中または複数ノード選択時は個別のUndoコマンドをプッシュしない
                selected_nodes = [item for item in self._view.scene.selectedItems() if isinstance(item, NodeItem)]
                is_multi_move = (len(selected_nodes) > 1 or 
                               getattr(self._view, '_is_multi_move_in_progress', False) or
                               getattr(self._view, '_is_multi_move_undo_pending', False))
                
                # デバッグ用のログ出力
                if is_multi_move:
                    print(f"複数ノード移動検出: 選択数={len(selected_nodes)}, 移動中={getattr(self._view, '_is_multi_move_in_progress', False)}, Undo保留={getattr(self._view, '_is_multi_move_undo_pending', False)}")
                    # 複数ノード移動時は個別のUndoコマンドをプッシュしない
                    return
                
                # 単一ノード移動の処理
                try:
                    from commands import MoveNodeCommand, MoveNodeWithRelatedCommand
                    if self._view._should_move_related_nodes(self, self.pos()):
                        # 重なる場合は関連ノードも移動
                        self._view.undo_stack.push(MoveNodeWithRelatedCommand(self._view, self, self._press_pos, self.pos()))
                    else:
                        # 重ならない場合は単純な移動のみ
                        self._view.undo_stack.push(MoveNodeCommand(self._view, self, self._press_pos, self.pos()))
                except ImportError:
                    # コマンドがインポートできない場合は直接移動
                    pass
        
        # 衝突がなければここでサブツリードラッグを終了
        if should_end_subtree_drag:
            self._view.end_subtree_drag()
        self._press_pos = None
        return super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """ダブルクリックでリネーム"""
        # テキスト編集中はダブルクリックイベントを無効化
        if self.text_editor.is_editing:
            return
        
        if not self.text_editor.is_editing:
            self.text_editor.start_editing()
        super().mouseDoubleClickEvent(event)