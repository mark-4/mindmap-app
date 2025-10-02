"""
ビュー関連のクラス
"""
import json
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QPainter,
    QUndoStack,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsLineItem,
)

from node import NodeItem
from connection import CrankConnection
from commands import (
    AddNodeCommand,
    ConnectNodesCommand,
    MoveNodeCommand,
    MoveMultipleNodesCommand,
    MoveNodeWithRelatedCommand,
    DeleteNodeCommand,
)


class MindMapView(QGraphicsView):
    """
    マインドマップのビューとシーンを管理するクラス
    
    このクラスは以下の機能を提供します：
    - QGraphicsSceneとQGraphicsViewの管理
    - ノードの配置とレイアウト計算
    - スマートな位置計算（衝突回避）
    - ズーム・パン・グリッド表示機能
    - ノード間の接続線（CrankConnection）の管理
    - アンドゥ・リドゥスタックの管理
    - ファイルの保存・読み込み機能
    
    主要なメソッド：
    - add_node(): ノードの追加
    - _calculate_smart_position(): スマートな位置計算
    - _calculate_parent_node_position(): 親ノードの位置計算
    - _get_subtree_bbox(): サブツリーの境界ボックス計算
    - _create_edge(): ノード間の接続線作成
    - set_zoom_speed(): ズーム速度の設定
    - set_transparency(): 透明度の設定
    """
    """マインドマップビュー"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        
        # 複数アイテム移動を有効にする
        self.setRubberBandSelectionMode(Qt.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.setSceneRect(QRectF(-2000, -2000, 4000, 4000))
        
        # シーンの背景を透明に設定
        self.scene.setBackgroundBrush(QBrush(Qt.transparent))
        
        # 背景透明化のための設定
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")

        # 接続モード用の状態（デフォルトでOFF、Shiftキーで操作）
        self.connect_mode_enabled = False
        self.pending_source_node: NodeItem | None = None
        self.undo_stack: QUndoStack | None = None
        
        # ズームスピードのパラメータ（デフォルト20%）
        self.zoom_speed = 1.20
        
        # ピンチジェスチャーを有効化
        self.grabGesture(Qt.GestureType.PinchGesture)
        
        # ピンチジェスチャーの初期スケール値
        self._pinch_scale_factor = 1.0
        
        # 透明度のパラメータ
        self.background_transparency = 1.0
        self.node_transparency = 1.0
        self.line_transparency = 1.0
        
        # グリッドのパラメータ
        self.grid_enabled = False
        self.grid_size = 20
        self.grid_snap_enabled = False
        
        # 複数ノード選択時の移動用
        self._multi_move_start_positions: dict[NodeItem, QPointF] = {}
        self._is_multi_move_in_progress = False
        
        # オートフィット機能
        self.auto_fit_enabled = False
        
        # 接続管理用のリスト
        self.connections: list[CrankConnection] = []

    def add_node(self, label: str = "ノード", pos: QPointF | None = None, is_parent_node: bool = False) -> NodeItem:
        """ノードを追加"""
        node = NodeItem(self, label)
        if pos is None:
            if is_parent_node:
                pos = self._calculate_parent_node_position()
            else:
                pos = self.mapToScene(self.viewport().rect().center())
        
        # 位置が指定されている場合は衝突検出を実行
        if pos is not None:
            all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
            pos = self._find_collision_free_position(pos, all_nodes)
        
        node.setPos(pos)
        node.setOpacity(self.node_transparency)
        self.scene.addItem(node)
        
        # オートフィットが有効な場合は自動的にフィット
        if self.auto_fit_enabled:
            self.fit_all_nodes()
        
        return node

    def wheelEvent(self, event):
        """マウスホイール・2本指スワイプでパン（スクロール）"""
        # 通常のスクロール処理
        super().wheelEvent(event)
    
    def event(self, event):
        """イベントハンドラー（ピンチジェスチャーを処理）"""
        if event.type() == event.Type.Gesture:
            return self.gestureEvent(event)
        return super().event(event)
    
    def gestureEvent(self, event):
        """ジェスチャーイベントを処理"""
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch:
            return self.pinchTriggered(pinch)
        return True
    
    def pinchTriggered(self, gesture):
        """ピンチジェスチャーでズーム"""
        from PySide6.QtWidgets import QPinchGesture
        
        if gesture.state() == Qt.GestureState.GestureStarted:
            # ジェスチャー開始時の初期化
            self._pinch_scale_factor = 1.0
        elif gesture.state() == Qt.GestureState.GestureUpdated or gesture.state() == Qt.GestureState.GestureFinished:
            # スケール変化を取得
            scale_factor = gesture.scaleFactor()
            
            # ズーム前のシーン上の位置を取得（ジェスチャーの中心点）
            center_point = gesture.centerPoint()
            old_pos = self.mapToScene(center_point.toPoint())
            
            # ズームを適用
            self.scale(scale_factor, scale_factor)
            
            # ズーム後の新しい位置を取得
            new_pos = self.mapToScene(center_point.toPoint())
            
            # 位置の差分を計算してビューを調整
            delta = new_pos - old_pos
            self.translate(delta.x(), delta.y())
        
        return True

    def set_zoom_speed(self, speed: float):
        """ズームスピードを設定"""
        if speed > 1.0:
            self.zoom_speed = speed

    def get_zoom_speed(self) -> float:
        """現在のズームスピードを取得"""
        return self.zoom_speed

    def set_background_transparency(self, transparency: float):
        """背景透明度を設定"""
        self.background_transparency = transparency
        if transparency < 1.0:
            self.scene.setBackgroundBrush(QBrush(Qt.transparent))
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
        else:
            self.scene.setBackgroundBrush(QBrush(Qt.white))
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self.setAttribute(Qt.WA_NoSystemBackground, False)
            self.setStyleSheet("QGraphicsView { background: white; border: none; }")

    def set_node_transparency(self, transparency: float):
        """ノード透明度を設定"""
        if 0.1 <= transparency <= 1.0:
            self.node_transparency = transparency
            for item in self.scene.items():
                if isinstance(item, NodeItem):
                    item.setOpacity(transparency)

    def set_line_transparency(self, transparency: float):
        """接続線透明度を設定"""
        if 0.1 <= transparency <= 1.0:
            self.line_transparency = transparency
            for item in self.scene.items():
                if isinstance(item, QGraphicsLineItem):
                    item.setOpacity(transparency)

    def get_background_transparency(self) -> float:
        """現在の背景透明度を取得"""
        return self.background_transparency

    def get_node_transparency(self) -> float:
        """現在のノード透明度を取得"""
        return self.node_transparency

    def get_line_transparency(self) -> float:
        """現在の接続線透明度を取得"""
        return self.line_transparency
    
    def set_grid_enabled(self, enabled: bool):
        """グリッド表示のON/OFFを設定"""
        self.grid_enabled = enabled
        self._update_grid_display()
    
    def get_grid_enabled(self) -> bool:
        """グリッド表示の状態を取得"""
        return self.grid_enabled
    
    def set_grid_snap_enabled(self, enabled: bool):
        """グリッドスナップのON/OFFを設定"""
        self.grid_snap_enabled = enabled
    
    def get_grid_snap_enabled(self) -> bool:
        """グリッドスナップの状態を取得"""
        return self.grid_snap_enabled
    
    def set_grid_size(self, size: int):
        """グリッドサイズを設定"""
        if size > 0:
            self.grid_size = size
            if self.grid_enabled:
                self._update_grid_display()
    
    def get_grid_size(self) -> int:
        """グリッドサイズを取得"""
        return self.grid_size
    
    def set_auto_fit_enabled(self, enabled: bool):
        """オートフィットのON/OFFを設定"""
        self.auto_fit_enabled = enabled
    
    def get_auto_fit_enabled(self) -> bool:
        """オートフィットの状態を取得"""
        return self.auto_fit_enabled
    
    def _is_any_node_editing(self) -> bool:
        """いずれかのノードがテキスト編集中かチェック"""
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                if hasattr(item, 'text_editor') and item.text_editor.is_editing:
                    return True
        return False
    
    def _update_grid_display(self):
        """グリッド表示を更新"""
        if self.grid_enabled:
            self.scene.setBackgroundBrush(self._create_grid_brush())
        else:
            self.scene.setBackgroundBrush(QBrush(Qt.transparent))
    
    def _create_grid_brush(self):
        """グリッドブラシを作成"""
        pixmap = QPixmap(self.grid_size, self.grid_size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.lightGray, 1))
        painter.drawLine(0, self.grid_size, self.grid_size, self.grid_size)
        painter.drawLine(self.grid_size, 0, self.grid_size, self.grid_size)
        painter.end()
        
        return QBrush(pixmap)
    
    def snap_to_grid(self, pos: QPointF) -> QPointF:
        """位置をグリッドにスナップ"""
        if not self.grid_snap_enabled:
            return pos
        
        grid_size = self.grid_size
        snapped_x = round(pos.x() / grid_size) * grid_size
        snapped_y = round(pos.y() / grid_size) * grid_size
        return QPointF(snapped_x, snapped_y)

    def fit_all_nodes(self):
        """全てのノードが画面に収まるように調整"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        if not all_nodes:
            return
        
        # 全てのノードの境界を計算
        rect = all_nodes[0].sceneBoundingRect()
        for node in all_nodes[1:]:
            rect = rect.united(node.sceneBoundingRect())
        
        # マージンを追加
        margin = 50
        rect.adjust(-margin, -margin, margin, margin)
        
        # ビューを調整
        self.fitInView(rect, Qt.KeepAspectRatio)

    def mousePressEvent(self, event):
        """マウスプレスイベント"""
        # 複数ノード選択時の移動開始位置を記録
        if event.button() == Qt.LeftButton:
            selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
            if len(selected_nodes) > 1:
                self._multi_move_start_positions.clear()
                self._is_multi_move_in_progress = True
                for node in selected_nodes:
                    self._multi_move_start_positions[node] = node.pos()
        
        # Shiftキーを押しながらのクリックでのみ接続モードを有効にする
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier:
            clicked_item = self.itemAt(event.pos())
            if isinstance(clicked_item, NodeItem):
                if self.pending_source_node is None:
                    self.pending_source_node = clicked_item
                    clicked_item.setSelected(True)
                else:
                    if clicked_item is not self.pending_source_node:
                        if self.undo_stack is not None:
                            self.undo_stack.push(ConnectNodesCommand(self, self.pending_source_node, clicked_item))
                        else:
                            self._create_edge(self.pending_source_node, clicked_item)
                    self.pending_source_node.setSelected(False)
                    self.pending_source_node = None
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """マウス移動イベント"""
        if self._is_multi_move_in_progress:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """マウスリリースイベント"""
        if event.button() == Qt.LeftButton and self._is_multi_move_in_progress:
            self._handle_multi_move_end()
        super().mouseReleaseEvent(event)

    def _handle_multi_move_end(self):
        """複数ノード移動の終了処理"""
        if not self._multi_move_start_positions:
            self._is_multi_move_in_progress = False
            return
        
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        
        if len(selected_nodes) <= 1:
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 移動量を計算
        moved_nodes = []
        delta_x = 0
        delta_y = 0
        
        for node in selected_nodes:
            if node in self._multi_move_start_positions:
                start_pos = self._multi_move_start_positions[node]
                current_pos = node.pos()
                node_delta_x = current_pos.x() - start_pos.x()
                node_delta_y = current_pos.y() - start_pos.y()
                
                if abs(node_delta_x) > 0.1 or abs(node_delta_y) > 0.1:
                    moved_nodes.append(node)
                    delta_x = node_delta_x
                    delta_y = node_delta_y
                    break
        
        if not moved_nodes:
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 移動距離が十分大きい場合のみUndoスタックに追加
        move_distance = (delta_x ** 2 + delta_y ** 2) ** 0.5
        
        if move_distance > 5.0 and self.undo_stack is not None:
            old_positions = []
            new_positions = []
            
            for node in selected_nodes:
                if node in self._multi_move_start_positions:
                    old_node_pos = self._multi_move_start_positions[node]
                else:
                    old_node_pos = node.pos()
                new_node_pos = QPointF(old_node_pos.x() + delta_x, old_node_pos.y() + delta_y)
                old_positions.append(old_node_pos)
                new_positions.append(new_node_pos)
            
            self.undo_stack.push(MoveMultipleNodesCommand(selected_nodes, old_positions, new_positions))
        
        # 状態をクリア
        self._is_multi_move_in_progress = False
        self._multi_move_start_positions.clear()

    def keyPressEvent(self, event):
        """キープレスイベント"""
        # テキスト編集中かチェック
        if self._is_any_node_editing():
            # テキスト編集中はEscapeキーのみ処理し、他はLineEditに渡す
            if event.key() == Qt.Key_Escape:
                # EscapeキーはLineEditで処理される
                pass
            # 他のキーはLineEditに渡すため、ここでは何もしない
            super().keyPressEvent(event)
            return
        
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_nodes()
        elif event.key() == Qt.Key_Tab:
            self._add_node_with_tab()
        elif event.key() == Qt.Key_Escape:
            if self.pending_source_node is not None:
                self.pending_source_node.setSelected(False)
                self.pending_source_node = None
        elif event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
            self._navigate_to_nearest_node(event.key())
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            self._select_all_nodes()
        else:
            super().keyPressEvent(event)

    def _select_all_nodes(self):
        """全てのノードを選択"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        if not all_nodes:
            return
        
        for node in all_nodes:
            node.setSelected(True)
        
        if hasattr(self.parent(), 'statusBar'):
            self.parent().statusBar().showMessage(f"{len(all_nodes)}個のノードを選択しました", 2000)

    def _delete_selected_nodes(self):
        """選択されたノードを削除"""
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            return
        
        if self.undo_stack is not None:
            for node in selected_nodes:
                self.undo_stack.push(DeleteNodeCommand(self, node))
        else:
            for node in selected_nodes:
                self.scene.removeItem(node)
        
        # オートフィットが有効な場合は自動的にフィット
        if self.auto_fit_enabled:
            self.fit_all_nodes()

    def _add_node_with_tab(self):
        """Tabキーでノード追加"""
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        
        if selected_nodes:
            parent_node = selected_nodes[0]
            new_pos = self._calculate_smart_position(parent_node)
            if self.undo_stack is not None:
                self.undo_stack.push(AddNodeCommand(self, "新規ノード", parent_node, new_pos, False))
            else:
                new_node = self.add_node("新規ノード", new_pos)
                self._create_edge(parent_node, new_node)
        else:
            if self.undo_stack is not None:
                self.undo_stack.push(AddNodeCommand(self, "新規ノード", None, None, True))
            else:
                self.add_node("新規ノード", None, True)

    def _create_edge(self, source: NodeItem, target: NodeItem) -> CrankConnection:
        """エッジを作成"""
        connection = CrankConnection(self.scene, source, target)
        source.attach_edge(connection, target)
        target.attach_edge(connection, source)
        # 接続をリストに追加
        self.connections.append(connection)
        return connection

    def remove_edge(self, connection: CrankConnection, source: NodeItem, target: NodeItem):
        """エッジを削除"""
        source.detach_edge(connection, target)
        target.detach_edge(connection, source)
        connection.remove()
        # 接続をリストから削除
        if connection in self.connections:
            self.connections.remove(connection)

    def _calculate_smart_position(self, parent_node: NodeItem) -> QPointF:
        """スマートな位置を計算（他の親ノードの子ノード群との衝突を考慮）"""
        # 親・子の幾何情報（シーン座標系）
        p_rect = parent_node.sceneBoundingRect()
        p_right = p_rect.right()
        p_y = parent_node.scenePos().y()
        
        # 新規ノードのサイズ（まだ配置前でも boundingRect() は取れる想定）
        node_w = 128.0
        node_h = 72.0
        
        H_GAP = 40   # 親→子の水平ギャップ（お好みで）
        V_GAP = 20   # 子同士の最小縦間隔
        
        def overlaps_vertically(a_rect, b_rect):
            """矩形の縦方向重なり判定（境界接触は重なりとみなさないなら < を <= に調整）"""
            return not (a_rect.bottom() <= b_rect.top() or a_rect.top() >= b_rect.bottom())
        
        # 既存の子ノードを取得
        child_nodes = []
        for connection, child in parent_node._edges:
            if child.pos().x() > parent_node.pos().x():
                child_nodes.append(child)
        
        # --- 衝突チェック：親の右側かつ同じ段（縦に重なる）に既存子がいるか？
        has_collision = False
        for ch in (child_nodes or []):
            ch_rect = ch.sceneBoundingRect()
            # 親の右側に存在（左端が親の右端以右）
            is_right_side = ch_rect.left() >= p_right
            # 新規ノードを「親と同じ段」に置く想定位置の縦帯
            tentative_y_center = p_y
            tentative_rect = QRectF(p_right + H_GAP, tentative_y_center - node_h/2, node_w, node_h)
            if is_right_side and overlaps_vertically(ch_rect, tentative_rect):
                has_collision = True
                break
        
        # --- 配置先を決める
        if has_collision:
            # 既存子の中で最も下にある矩形の更に下に配置
            lowest_bottom = p_rect.bottom()  # 念のため親の下端も初期値に
            for ch in child_nodes:
                ch_rect = ch.sceneBoundingRect()
                if ch_rect.bottom() > lowest_bottom:
                    lowest_bottom = ch_rect.bottom()
            target_y = lowest_bottom + V_GAP + node_h/2
        else:
            # 衝突なし：親と同じ段（同じY）
            target_y = p_y
        
        target_x = p_right + H_GAP + node_w/2
        
        # グリッドスナップが有効な場合は適用
        if self.get_grid_snap_enabled():
            snapped_pos = self.snap_to_grid(QPointF(target_x, target_y))
            return snapped_pos
        
        return QPointF(target_x, target_y)

    

    def _calculate_parent_node_position(self) -> QPointF:
        """新しい親ノードの配置位置を計算（既存の親ノードの子ノード群の下に配置）"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        if not all_nodes:
            return self.mapToScene(self.viewport().rect().center())
        
        # 中心ノードを特定（最も左側にあるノード）
        center_node = None
        leftmost_x = float('inf')
        for node in all_nodes:
            if node.pos().x() < leftmost_x:
                leftmost_x = node.pos().x()
                center_node = node
        
        if center_node is None:
            return self.mapToScene(self.viewport().rect().center())
        
        # 新しい配置ロジックを使用
        return self._calculate_parent_insert_position(center_node)
    
    def _get_subtree_bbox(self, root_node: NodeItem, include_descendants: bool = True) -> dict:
        """サブツリーの境界ボックスを計算"""
        if root_node is None:
            return {"x": 0, "y": 0, "width": 0, "height": 0, "bottom": 0}
        
        # ノードのサイズを取得
        node_rect = root_node.rect()
        node_width = node_rect.width()
        node_height = node_rect.height()
        node_pos = root_node.pos()
        
        # 初期値はルートノードの境界
        min_x = node_pos.x()
        min_y = node_pos.y()
        max_x = node_pos.x() + node_width
        max_y = node_pos.y() + node_height
        
        if include_descendants:
            # 子ノードを再帰的に取得
            child_nodes = self._get_child_nodes(root_node)
            for child in child_nodes:
                child_bbox = self._get_subtree_bbox(child, True)
                min_x = min(min_x, child_bbox["x"])
                min_y = min(min_y, child_bbox["y"])
                max_x = max(max_x, child_bbox["x"] + child_bbox["width"])
                max_y = max(max_y, child_bbox["y"] + child_bbox["height"])
        
        return {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
            "bottom": max_y
        }
    
    def _get_child_nodes(self, parent_node: NodeItem) -> list[NodeItem]:
        """指定されたノードの子ノードを取得"""
        child_nodes = []
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        for node in all_nodes:
            if node == parent_node:
                continue
            
            # 接続を確認して子ノードかどうか判定
            for connection in self.connections:
                if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                    connection.source == parent_node and connection.target == node):
                    child_nodes.append(node)
                    break
        
        return child_nodes
    
    def _check_collision(self, bbox: dict, exclude_node: NodeItem = None) -> bool:
        """指定された境界ボックスが他のノードと衝突するかチェック"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        for node in all_nodes:
            if node == exclude_node:
                continue
            
            node_rect = node.rect()
            node_pos = node.pos()
            node_bbox = {
                "x": node_pos.x(),
                "y": node_pos.y(),
                "width": node_rect.width(),
                "height": node_rect.height()
            }
            
            # 境界ボックスの重なりをチェック
            if (bbox["x"] < node_bbox["x"] + node_bbox["width"] and
                bbox["x"] + bbox["width"] > node_bbox["x"] and
                bbox["y"] < node_bbox["y"] + node_bbox["height"] and
                bbox["y"] + bbox["height"] > node_bbox["y"]):
                return True
        
        return False
    
    def _push_down_until_no_collision(self, bbox: dict, step: float = 40.0, exclude_node: NodeItem = None) -> dict:
        """衝突がなくなるまで下方向にプッシュ"""
        original_bbox = bbox.copy()
        
        while self._check_collision(bbox, exclude_node):
            bbox["y"] += step
            bbox["bottom"] = bbox["y"] + bbox["height"]
        
        return bbox
    
    def _calculate_parent_insert_position(self, reference_parent: NodeItem) -> QPointF:
        """新しい親ノードの挿入位置を計算（すべての既存親ノードの子ノード群との衝突を考慮）"""
        # 定数
        VERTICAL_GAP = 60.0  # 垂直間隔
        PARENT_COLUMN_OFFSET = 200.0  # 親ノード列のXオフセット
        NODE_WIDTH = 128.0  # ノードの幅
        NODE_HEIGHT = 72.0  # ノードの高さ
        
        # すべての既存の親ノードを取得
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        all_parent_nodes = self._get_all_parent_nodes(all_nodes)
        
        # すべての親ノードのサブツリーの最下端を計算
        max_bottom_y = reference_parent.pos().y()  # 初期値は参照親ノードのY座標
        for parent in all_parent_nodes:
            subtree_bbox = self._get_subtree_bbox(parent, True)
            max_bottom_y = max(max_bottom_y, subtree_bbox["bottom"])
        
        # 新しい親ノードの配置位置を計算
        new_parent_x = reference_parent.pos().x() + PARENT_COLUMN_OFFSET
        new_parent_y = max_bottom_y + VERTICAL_GAP
        
        # 新しい親ノードの境界ボックスを作成
        new_parent_bbox = {
            "x": new_parent_x,
            "y": new_parent_y,
            "width": NODE_WIDTH,
            "height": NODE_HEIGHT,
            "bottom": new_parent_y + NODE_HEIGHT
        }
        
        # 最終的な衝突回避（他のノードとの重なりをチェック）
        final_bbox = self._push_down_until_no_collision(new_parent_bbox)
        
        # グリッドスナップが有効な場合は適用
        if self.get_grid_snap_enabled():
            snapped_pos = self.snap_to_grid(QPointF(final_bbox["x"], final_bbox["y"]))
            return snapped_pos
        
        return QPointF(final_bbox["x"], final_bbox["y"])
    
    def _get_all_parent_nodes(self, all_nodes: list[NodeItem]) -> list[NodeItem]:
        """すべての親ノードを取得（中心ノードとその他の親ノード）"""
        parent_nodes = []
        
        # 中心ノード（最も左側のノード）を特定
        center_node = None
        leftmost_x = float('inf')
        for node in all_nodes:
            if node.pos().x() < leftmost_x:
                leftmost_x = node.pos().x()
                center_node = node
        
        if center_node:
            parent_nodes.append(center_node)
        else:
            return parent_nodes
        
        # 中心ノードから直接接続されている子ノードを特定
        child_nodes = self._get_child_nodes(center_node)
        
        # 修正: 中心ノードから直接接続されている子ノードを親ノードとして扱う
        # これらは実際には子ノードだが、新しい親ノードの配置計算では親ノードとして扱う
        for child in child_nodes:
            parent_nodes.append(child)
        
        return parent_nodes
    
    def _is_connected_to_center(self, node: NodeItem, center_node: NodeItem) -> bool:
        """指定されたノードが中心ノードに接続されているかチェック"""
        if not center_node:
            return False
        
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                ((connection.source == center_node and connection.target == node) or
                 (connection.source == node and connection.target == center_node))):
                return True
        return False

    def _find_collision_free_position(self, pos: QPointF, all_nodes: list[NodeItem]) -> QPointF:
        """衝突しない位置を検索"""
        node_width = 128
        node_height = 72
        min_spacing = 20
        
        # 指定位置が空いているかチェック
        if self._is_position_free(pos, node_width, node_height, min_spacing, all_nodes):
            return pos
        
        # 螺旋状に検索
        return self._find_nearest_free_position(pos, node_width, node_height, min_spacing, all_nodes)

    def _is_position_free(self, pos: QPointF, node_width: float, node_height: float, min_spacing: float, all_nodes: list[NodeItem]) -> bool:
        """位置が空いているかチェック"""
        test_rect = QRectF(pos.x() - node_width/2 - min_spacing, 
                          pos.y() - node_height/2 - min_spacing,
                          node_width + min_spacing*2, 
                          node_height + min_spacing*2)
        
        for node in all_nodes:
            node_rect = node.sceneBoundingRect()
            if test_rect.intersects(node_rect):
                return False
        return True

    def _find_nearest_free_position(self, center_pos: QPointF, node_width: float, node_height: float, min_spacing: float, all_nodes: list[NodeItem]) -> QPointF:
        """最も近い空いている位置を検索"""
        step = 50
        max_radius = 1000
        
        for radius in range(step, max_radius, step):
            for angle in range(0, 360, 30):
                import math
                x = center_pos.x() + radius * math.cos(math.radians(angle))
                y = center_pos.y() + radius * math.sin(math.radians(angle))
                test_pos = QPointF(x, y)
                
                if self._is_position_free(test_pos, node_width, node_height, min_spacing, all_nodes):
                    return test_pos
        
        # 見つからない場合は中心位置を返す
        return center_pos

    def _is_position_free_for_node(self, pos: QPointF, moving_node: NodeItem) -> bool:
        """移動するノード用の位置チェック"""
        try:
            node_width = 128
            node_height = 72
            min_spacing = 20
            
            test_rect = QRectF(pos.x() - node_width/2 - min_spacing, 
                              pos.y() - node_height/2 - min_spacing,
                              node_width + min_spacing*2, 
                              node_height + min_spacing*2)
            
            all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
            
            for node in all_nodes:
                if node == moving_node:
                    continue
                
                node_rect = node.sceneBoundingRect()
                if test_rect.intersects(node_rect):
                    return False
            
            return True
        except Exception:
            return True

    def _should_move_related_nodes(self, moved_node: NodeItem, new_pos: QPointF) -> bool:
        """関連ノードを移動すべきかチェック"""
        return False  # 簡略化のため常にFalse

    def _calculate_node_level(self, node: NodeItem, all_nodes: list[NodeItem]) -> int:
        """ノードの階層レベルを計算"""
        return 0  # 簡略化のため常に0

    def _navigate_to_nearest_node(self, direction: Qt.Key):
        """最寄りのノードに移動"""
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            return
        
        current_node = selected_nodes[0]
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        if len(all_nodes) <= 1:
            return
        
        # 方向に応じて最寄りのノードを検索
        nearest_node = None
        min_distance = float('inf')
        
        for node in all_nodes:
            if node == current_node:
                continue
            
            dx = node.pos().x() - current_node.pos().x()
            dy = node.pos().y() - current_node.pos().y()
            
            if direction == Qt.Key_Up and dy < 0:
                distance = (dx*dx + dy*dy) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    nearest_node = node
            elif direction == Qt.Key_Down and dy > 0:
                distance = (dx*dx + dy*dy) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    nearest_node = node
            elif direction == Qt.Key_Left and dx < 0:
                distance = (dx*dx + dy*dy) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    nearest_node = node
            elif direction == Qt.Key_Right and dx > 0:
                distance = (dx*dx + dy*dy) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    nearest_node = node
        
        if nearest_node:
            current_node.setSelected(False)
            nearest_node.setSelected(True)
            # ビューをスクロール
            self.centerOn(nearest_node)

    def _export_to_json(self) -> str:
        """JSONにエクスポート"""
        data = {
            "nodes": [],
            "edges": []
        }
        
        # ノード情報を収集
        node_id_map = {}
        for i, item in enumerate(self.scene.items()):
            if isinstance(item, NodeItem):
                node_id = f"node_{i}"
                node_id_map[item] = node_id
                data["nodes"].append({
                    "id": node_id,
                    "text": item.text_item.toPlainText(),
                    "x": item.pos().x(),
                    "y": item.pos().y()
                })
        
        # エッジ情報を収集
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                for connection, other_node in item._edges:
                    if item in node_id_map and other_node in node_id_map:
                        data["edges"].append({
                            "source": node_id_map[item],
                            "target": node_id_map[other_node]
                        })
        
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _import_from_json(self, json_str: str):
        """JSONからインポート"""
        try:
            data = json.loads(json_str)
            
            # シーンをクリア
            self.scene.clear()
            if self.undo_stack:
                self.undo_stack.clear()
            
            # ノードを作成
            node_map = {}
            for node_data in data.get("nodes", []):
                node = self.add_node(
                    node_data["text"],
                    QPointF(node_data["x"], node_data["y"])
                )
                node_map[node_data["id"]] = node
            
            # エッジを作成
            for edge_data in data.get("edges", []):
                source = node_map.get(edge_data["source"])
                target = node_map.get(edge_data["target"])
                if source and target:
                    self._create_edge(source, target)
        
        except Exception as e:
            print(f"JSONインポートエラー: {e}")
