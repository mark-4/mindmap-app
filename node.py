"""
ノード関連のクラス
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsTextItem,
    QGraphicsItem,
)

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
        
        # 位置変更後にライン更新
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._update_attached_lines()
        # 選択状態の変化を検知して枠線の太さを調整
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self._update_selection_style()
        
        return super().itemChange(change, value)
    
    def mousePressEvent(self, event):
        """マウスプレスイベント"""
        # テキスト編集中はマウスイベントを無効化
        if self.text_editor.is_editing:
            return
        self._press_pos = self.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """マウスリリースイベント"""
        # テキスト編集中はマウスイベントを無効化
        if self.text_editor.is_editing:
            return
        
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
            
            # 移動距離が十分大きい場合のみUndoスタックに追加
            move_distance = ((self.pos().x() - self._press_pos.x()) ** 2 + 
                           (self.pos().y() - self._press_pos.y()) ** 2) ** 0.5
            
            if move_distance > 5.0 and self._view.undo_stack is not None:
                # 単一ノード移動の処理
                try:
                    from commands import MoveNodeCommand, MoveNodeWithRelatedCommand
                    if self._view._should_move_related_nodes(self, self.pos()):
                        # 重なる場合は関連ノードも移動
                        self._view.undo_stack.push(MoveNodeWithRelatedCommand(self._view, self, self._press_pos, self.pos()))
                    else:
                        # 重ならない場合は単純な移動のみ
                        self._view.undo_stack.push(MoveNodeCommand(self, self._press_pos, self.pos()))
                except ImportError:
                    # コマンドがインポートできない場合は直接移動
                    pass
        
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
    
