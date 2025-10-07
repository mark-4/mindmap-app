"""
ビュー関連のクラス
"""
import json
import random
import math
from node import NodeItem
from PySide6.QtCore import QRectF, QPointF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QPainter,
    QPen,
    QUndoStack,
    QKeySequence,
    QPixmap,
    QAction,
    QColor,
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
    RenameNodeCommand,
    SubtreeMoveCommand,
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
        
        # レイアウト定数
        self.VERTICAL_GAP = 60.0  # 垂直間隔
        self.PARENT_COLUMN_OFFSET = 200.0  # 親ノード列のXオフセット
        self.NODE_WIDTH = 128.0  # ノードの幅
        self.NODE_HEIGHT = 72.0  # ノードの高さ
        
        # サブツリードラッグ機能の状態管理
        self._subtree_drag_mode = False
        self._subtree_drag_root = None
        self._subtree_drag_start_pos = None
        self._subtree_drag_snapshot = {}  # {node: original_position}
        self._subtree_drag_edges_snapshot = {}  # {connection: original_control_points}
        
        # 透明度のパラメータ
        self.background_transparency = 1.0
        self.node_transparency = 1.0
        self.line_transparency = 1.0
        self.window_transparency = 1.0
        
        # グリッドのパラメータ
        self.grid_enabled = False
        self.grid_size = 20  # より適切なグリッドサイズに変更
        self.grid_snap_enabled = True
        self.snap_threshold = 10.0   # スナップ閾値（グリッドサイズの50%）
        self.snap_strength = 1.0    # スナップ強度（完全スナップ）
        
        # 複数ノード選択時の移動用
        self._multi_move_start_positions: dict[NodeItem, QPointF] = {}
        self._is_multi_move_undo_pending = False
        self._is_multi_move_in_progress = False
        
        # Shiftキー状態の追跡
        self._shift_key_pressed = False
        
        # アトラクションモード用
        self._attraction_mode = False
        self._attraction_timer = QTimer()
        self._attraction_timer.timeout.connect(self._update_attraction)
        self._original_positions = {}  # ノードの元の位置を保存
        self._original_connections = {}  # 接続線の元の状態を保存
        
        # オートフィット機能
        self.auto_fit_enabled = False
        
        # 接続管理用のリスト
        self.connections: list[CrankConnection] = []
        
        # 整理（整列）設定
        self.ALIGN_MIN_GAP = 5.0  # 最小間隔
        self.LANE_X_SPACING = 180.0  # 世代ごとのX間隔（左端整列のための基準）

    def align_generations_and_avoid_line_overlap(self) -> None:
        """同世代の左端X整列＋接続線重なり回避の最小オフセット配置を行う。"""
        try:
            all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
            if not all_nodes:
                return
            # 中心ノード（最も左）
            center_node = min(all_nodes, key=lambda n: n.pos().x())
            # BFSで世代を分類
            generations: dict[int, list[NodeItem]] = {0: [center_node]}
            visited = {center_node}
            queue = [(center_node, 0)]
            while queue:
                cur, level = queue.pop(0)
                for conn in self.connections:
                    if not (hasattr(conn, 'source') and hasattr(conn, 'target')):
                        continue
                    if conn.source == cur and conn.target not in visited:
                        generations.setdefault(level+1, []).append(conn.target)
                        visited.add(conn.target)
                        queue.append((conn.target, level+1))

            # 各世代を左端Xで整列
            base_x = center_node.pos().x()
            for level, nodes in generations.items():
                target_left_x = base_x + level * self.LANE_X_SPACING
                # Y順に安定化
                nodes.sort(key=lambda n: n.pos().y())
                for n in nodes:
                    rect = n.boundingRect()
                    target_center_x = target_left_x + rect.width()/2.0
                    n.setPos(target_center_x, n.pos().y())

            # 縦線（vertical_line）のXが重ならないよう最小オフセット
            # 同一世代内で、親のvertical_xが近接・重複する場合に右へ微オフセット
            for level, nodes in generations.items():
                if not nodes:
                    continue
                # vertical_xの推定: ノード右端+20（connectionの仕様に合わせる）
                pairs = []  # (node, vertical_x)
                for n in nodes:
                    vr = n.sceneBoundingRect().right() + 20
                    pairs.append([n, vr])
                # vertical_x昇順で調整
                pairs.sort(key=lambda p: p[1])
                min_dx = 6.0  # 重なり回避の最小水平オフセット
                for i in range(1, len(pairs)):
                    prev_vx = pairs[i-1][1]
                    cur_vx = pairs[i][1]
                    if cur_vx <= prev_vx:
                        # 直前より右にずらす
                        delta = (prev_vx + min_dx) - cur_vx
                        n = pairs[i][0]
                        n.setPos(n.pos().x() + delta, n.pos().y())
                        # 更新後のvertical_xも反映
                        pairs[i][1] = cur_vx + delta

            # 最後に最小ギャップ5pxで上下の重なりを解消（同一世代ごと）
            for level, nodes in generations.items():
                nodes.sort(key=lambda n: n.pos().y())
                if not nodes:
                    continue
                prev = nodes[0]
                prev_bottom = prev.pos().y() + prev.boundingRect().height()/2.0
                for n in nodes[1:]:
                    cur_top = n.pos().y() - n.boundingRect().height()/2.0
                    required_top = prev_bottom + self.ALIGN_MIN_GAP
                    if cur_top < required_top:
                        dy = required_top - cur_top
                        self._translate_subtree_vertical(n, dy)
                    prev_bottom = n.pos().y() + n.boundingRect().height()/2.0

            # 接続線更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
            self.scene.update()
        except Exception as e:
            print(f"align_generations_and_avoid_line_overlap エラー: {e}")

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
        
        # レイアウトの再計算と再描画
        self.relayout()
        
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
        if 0.0 <= transparency <= 1.0:
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
    
    def set_window_transparency(self, transparency: float):
        """ウィンドウ透明度を設定"""
        if 0.1 <= transparency <= 1.0:
            self.window_transparency = transparency
            # 親ウィンドウの透明度を設定
            parent_window = self.window()
            if parent_window:
                parent_window.setWindowOpacity(transparency)

    def get_background_transparency(self) -> float:
        """現在の背景透明度を取得"""
        return self.background_transparency

    def get_node_transparency(self) -> float:
        """現在のノード透明度を取得"""
        return self.node_transparency

    def get_line_transparency(self) -> float:
        """現在の接続線透明度を取得"""
        return self.line_transparency
    
    def get_window_transparency(self) -> float:
        """現在のウィンドウ透明度を取得"""
        return self.window_transparency
    
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
    
    def set_snap_threshold(self, threshold: float):
        """スナップ閾値を設定"""
        self.snap_threshold = threshold
    
    def set_snap_strength(self, strength: float):
        """スナップ強度を設定（0.0-1.0）"""
        self.snap_strength = max(0.0, min(1.0, strength))
    
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
        # シーンの再描画を強制
        self.scene.update()
    
    def _create_grid_brush(self):
        """グリッドブラシを作成（100px毎に色を変える）"""
        # 100pxの倍数でグリッドサイズを調整
        major_grid_size = 100
        minor_grid_size = self.grid_size
        
        # パターンサイズを100pxの倍数に設定（最小100px）
        pattern_size = max(major_grid_size, minor_grid_size)
        # 100pxの倍数に調整
        pattern_size = ((pattern_size - 1) // major_grid_size + 1) * major_grid_size
        
        pixmap = QPixmap(pattern_size, pattern_size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        
        # 薄いグリッド線（通常のグリッド）
        painter.setPen(QPen(QColor(200, 200, 200, 100), 1))  # 薄いグレー
        for i in range(0, pattern_size, minor_grid_size):
            if i % major_grid_size != 0:  # 100pxの倍数でない場合のみ
                painter.drawLine(i, 0, i, pattern_size - 1)
                painter.drawLine(0, i, pattern_size - 1, i)
        
        # 濃いグリッド線（100px毎）
        painter.setPen(QPen(QColor(150, 150, 150, 200), 1))  # 濃いグレー
        for i in range(0, pattern_size + 1, major_grid_size):
            painter.drawLine(i, 0, i, pattern_size)
            painter.drawLine(0, i, pattern_size, i)
        
        painter.end()
        
        brush = QBrush(pixmap)
        brush.setTransform(brush.transform().translate(0, 0))
        return brush
    
    def snap_to_grid(self, pos: QPointF, threshold: float = None) -> QPointF:
        """位置をグリッドにスナップ（カクカクしたスナップ）"""
        if not self.grid_snap_enabled:
            return pos
        
        grid_size = self.grid_size
        if threshold is None:
            threshold = self.snap_threshold
        
        # グリッド位置を計算（ノードの中心をグリッド線に合わせる）
        grid_x = round(pos.x() / grid_size) * grid_size
        grid_y = round(pos.y() / grid_size) * grid_size
        
        # 閾値内の場合のみスナップ
        dx = abs(pos.x() - grid_x)
        dy = abs(pos.y() - grid_y)
        
        # X軸とY軸を個別にチェック（より積極的なスナップ）
        snap_x = pos.x()
        snap_y = pos.y()
        
        if dx <= threshold:
            snap_x = grid_x
        if dy <= threshold:
            snap_y = grid_y
        
        return QPointF(snap_x, snap_y)

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

    def start_attraction_mode(self):
        """アトラクションモードを開始"""
        if self._attraction_mode:
            return
        
        self._attraction_mode = True
        
        # 全てのノードの元の位置を保存
        self._original_positions.clear()
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        for node in all_nodes:
            self._original_positions[node] = node.pos()
        
        # 全ての接続線の元の状態を保存
        self._original_connections.clear()
        for connection in self.connections:
            if hasattr(connection, 'source') and hasattr(connection, 'target'):
                # 接続線の詳細な状態を保存
                connection_data = {
                    'source': connection.source,
                    'target': connection.target,
                    'horizontal_line1_line': connection.horizontal_line1.line() if connection.horizontal_line1 else None,
                    'vertical_line_line': connection.vertical_line.line() if connection.vertical_line else None,
                    'horizontal_line2_line': connection.horizontal_line2.line() if connection.horizontal_line2 else None,
                }
                self._original_connections[id(connection)] = connection_data
        
        # タイマーを開始（30FPS）
        self._attraction_timer.start(33)  # 約30FPS

    def stop_attraction_mode(self):
        """アトラクションモードを終了"""
        if not self._attraction_mode:
            return
        
        self._attraction_mode = False
        self._attraction_timer.stop()
        
        # 全てのノードを元の位置に戻す
        for node, original_pos in self._original_positions.items():
            node.setPos(original_pos)
        
        # ノード位置の復元後にシーンを一度更新
        self.scene.update()
        
        # 全ての接続線を元の状態に戻す
        for connection in self.connections:
            connection_id = id(connection)
            if connection_id in self._original_connections:
                # 保存された接続線の状態を復元
                original_data = self._original_connections[connection_id]
                if connection.horizontal_line1 and original_data['horizontal_line1_line']:
                    connection.horizontal_line1.setLine(original_data['horizontal_line1_line'])
                if connection.vertical_line and original_data['vertical_line_line']:
                    connection.vertical_line.setLine(original_data['vertical_line_line'])
                if connection.horizontal_line2 and original_data['horizontal_line2_line']:
                    connection.horizontal_line2.setLine(original_data['horizontal_line2_line'])
            else:
                # フォールバック: 通常の更新
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        
        # 最終的なシーンの更新
        self.scene.update()
        
        # 元の位置と接続線の状態をクリア
        self._original_positions.clear()
        self._original_connections.clear()

    def _update_attraction(self):
        """アトラクションモードの更新処理"""
        if not self._attraction_mode:
            return
        
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        if not all_nodes:
            return
        
        # ビューのサイズを取得
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        for node in all_nodes:
            # 現在の位置を取得
            current_pos = node.pos()
            
            # ランダムな移動量を生成
            move_x = random.uniform(-5, 5)
            move_y = random.uniform(-5, 5)
            
            # 新しい位置を計算
            new_x = current_pos.x() + move_x
            new_y = current_pos.y() + move_y
            
            # ビューの境界内に制限
            node_width = node.boundingRect().width()
            node_height = node.boundingRect().height()
            
            new_x = max(view_rect.left() + node_width/2, 
                       min(view_rect.right() - node_width/2, new_x))
            new_y = max(view_rect.top() + node_height/2, 
                       min(view_rect.bottom() - node_height/2, new_y))
            
            # ノードの位置を更新
            node.setPos(new_x, new_y)
        
        # 接続線を更新
        for connection in self.connections:
            if hasattr(connection, 'update_connection'):
                connection.update_connection()
        
        # シーンを更新
        self.scene.update()

    def mousePressEvent(self, event):
        """マウスプレスイベント"""
        # 複数ノード選択時の移動開始位置を記録
        if event.button() == Qt.LeftButton:
            selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
            if len(selected_nodes) > 1:
                self._multi_move_start_positions.clear()
                self._is_multi_move_in_progress = True
                self._is_multi_move_undo_pending = False  # リセット
                for node in selected_nodes:
                    self._multi_move_start_positions[node] = node.pos()
        
        # Shiftキーを押しながらのクリックでのみ接続モードを有効にする
        if event.button() == Qt.LeftButton and (event.modifiers() & Qt.ShiftModifier):
            clicked_item = self.itemAt(event.pos())
            if isinstance(clicked_item, NodeItem):
                if self.pending_source_node is None:
                    # 接続の始点を設定
                    self.pending_source_node = clicked_item
                    clicked_item.setSelected(True)
                else:
                    # 接続の終点を設定し、エッジ作成
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
            # 複数ノード移動中の接続線更新
            selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
            for connection in self.connections:
                if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                    (connection.source in selected_nodes or connection.target in selected_nodes)):
                    # 接続線の更新メソッドを呼び出し
                    if hasattr(connection, 'update_connection'):
                        connection.update_connection()
            # シーンの再描画
            self.scene.update()
        
        
        super().mouseMoveEvent(event)
    
    
    def keyPressEvent(self, event):
        """キー押下イベント"""
        if event.key() == Qt.Key_Shift:
            # Shiftキーが押された場合の処理
            self._shift_key_pressed = True
            # ステータスバーにメッセージを表示
            if hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage("Shiftキー: 単独ノード移動モード")
        elif event.key() == Qt.Key_Escape:
            # ESCキーでアトラクションモードを終了
            if self._attraction_mode:
                self.stop_attraction_mode()
                # ボタンの状態も更新
                parent_window = self.window()
                if parent_window:
                    # ツールバーからアトラクションボタンを探して状態を更新
                    for action in parent_window.findChildren(QAction):
                        if action.text() == "アトラクション":
                            action.setChecked(False)
                            break
                    # ステータスバーにメッセージを表示
                    if hasattr(parent_window, 'statusBar') and parent_window.statusBar():
                        parent_window.statusBar().showMessage("アトラクション: OFF")
        super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """キーリリースイベント"""
        if event.key() == Qt.Key_Shift:
            # Shiftキーが離された場合の処理
            self._shift_key_pressed = False
            # ステータスバーメッセージをクリア
            if hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().clearMessage()
        super().keyReleaseEvent(event)

    def mouseReleaseEvent(self, event):
        """マウスリリースイベント"""
        if event.button() == Qt.LeftButton and self._is_multi_move_in_progress:
            # 複数ノード移動の終了処理（一度だけ実行）
            # タイマーを使用して、全てのmouseReleaseEventが完了してから実行
            if not hasattr(self, '_multi_move_end_timer'):
                self._multi_move_end_timer = QTimer()
                self._multi_move_end_timer.setSingleShot(True)
                self._multi_move_end_timer.timeout.connect(self._handle_multi_move_end)
            
            # 10ms後に実行（全てのmouseReleaseEventが完了するまで待機）
            self._multi_move_end_timer.start(10)
        super().mouseReleaseEvent(event)

    def _handle_multi_move_end(self):
        """複数ノード移動の終了処理"""
        # 重複実行を防ぐ
        if not self._is_multi_move_in_progress or self._is_multi_move_undo_pending:
            return
            
        if not self._multi_move_start_positions:
            self._is_multi_move_in_progress = False
            return
        
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        
        if len(selected_nodes) <= 1:
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 各ノードの移動量を個別に計算
        old_positions = []
        new_positions = []
        has_movement = False
        
        for node in selected_nodes:
            if node in self._multi_move_start_positions:
                old_pos = self._multi_move_start_positions[node]
                new_pos = node.pos()
                
                # 移動距離をチェック
                move_distance = ((new_pos.x() - old_pos.x()) ** 2 + (new_pos.y() - old_pos.y()) ** 2) ** 0.5
                if move_distance > 1.0:
                    has_movement = True
                
                old_positions.append(old_pos)
                new_positions.append(new_pos)
            else:
                # 開始位置が記録されていない場合は現在位置を使用
                current_pos = node.pos()
                old_positions.append(current_pos)
                new_positions.append(current_pos)
        
        # 衝突検出：選択ノード群のいずれかが他ノードに重なる場合は全体を元位置に戻す
        collision_detected = False
        if has_movement:
            try:
                from node import NodeItem  # 遅延インポート
                margin = 5
                for n in selected_nodes:
                    # nの現在位置での矩形
                    n_rect = QRectF(
                        n.pos().x() - n.boundingRect().width() / 2.0,
                        n.pos().y() - n.boundingRect().height() / 2.0,
                        n.boundingRect().width(),
                        n.boundingRect().height(),
                    )
                    for item in self.scene.items():
                        if isinstance(item, NodeItem) and item not in selected_nodes:
                            item_rect = item.sceneBoundingRect()
                            expanded_rect = QRectF(
                                item_rect.x() - margin,
                                item_rect.y() - margin,
                                item_rect.width() + 2 * margin,
                                item_rect.height() + 2 * margin,
                            )
                            if n_rect.intersects(expanded_rect):
                                collision_detected = True
                    break
                    if collision_detected:
                        break
            except Exception as e:
                print(f"複数移動 衝突検出エラー: {e}")

        if collision_detected:
            # 元位置に一括ロールバック
            for node in selected_nodes:
                if node in self._multi_move_start_positions:
                    node.setPos(self._multi_move_start_positions[node])
            # 接続線更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
            self.scene.update()
            # 状態リセット
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 移動があった場合のみUndoスタックに追加（衝突が無い場合）
        if has_movement and self.undo_stack is not None and not self._is_multi_move_undo_pending:
            print(f"複数ノード移動Undoコマンドをプッシュ: {len(selected_nodes)}個のノード")
            self.undo_stack.push(MoveMultipleNodesCommand(self, selected_nodes, old_positions, new_positions))
            self._is_multi_move_undo_pending = True
        elif has_movement:
            print(f"複数ノード移動Undoコマンドをスキップ: has_movement={has_movement}, undo_stack={self.undo_stack is not None}, pending={self._is_multi_move_undo_pending}")
        else:
            print(f"複数ノード移動Undoコマンドをスキップ: 移動なし (has_movement={has_movement})")
        
        # 移動したノードに関連する接続線を更新
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source in selected_nodes or connection.target in selected_nodes)):
                # 接続線の更新メソッドを呼び出し
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        
        # 状態をクリア
        self._is_multi_move_in_progress = False
        self._multi_move_start_positions.clear()
        self._is_multi_move_undo_pending = False
        
        # シーンの再描画
        self.scene.update()

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
                # 新しく作成されたノードを選択
                for item in self.scene.selectedItems():
                    item.setSelected(False)
                new_node.setSelected(True)
        else:
            if self.undo_stack is not None:
                self.undo_stack.push(AddNodeCommand(self, "新規ノード", None, None, True))
            else:
                new_node = self.add_node("新規ノード", None, True)
                # 新しく作成されたノードを選択
                for item in self.scene.selectedItems():
                    item.setSelected(False)
                new_node.setSelected(True)

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
        return self.calculate_parent_insert_position(center_node)
    
    def get_subtree_bbox(self, root_node: NodeItem, include_descendants: bool = True) -> dict:
        """
        サブツリーの境界ボックスを計算
        
        Args:
            root_node: ルートノード
            include_descendants: 子孫ノードを含めるかどうか
            
        Returns:
            BBox辞書: {x, y, width, height, bottom}
        """
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
                child_bbox = self.get_subtree_bbox(child, True)
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
    
    def _get_subtree_bbox(self, root_node: NodeItem, include_descendants: bool = True) -> dict:
        """後方互換性のためのエイリアス"""
        return self.get_subtree_bbox(root_node, include_descendants)
    
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
    
    def get_descendants(self, root_node: NodeItem) -> list[NodeItem]:
        """
        指定されたノードの子孫ノード（子、孫、曾孫など）を再帰的に取得
        
        Args:
            root_node: ルートノード
            
        Returns:
            list[NodeItem]: 子孫ノードのリスト
        """
        descendants = []
        child_nodes = self._get_child_nodes(root_node)
        
        for child in child_nodes:
            descendants.append(child)
            # 再帰的に子孫ノードを取得
            descendants.extend(self.get_descendants(child))
        
        return descendants
    
    def begin_subtree_drag(self, root_node: NodeItem):
        """
        サブツリードラッグを開始
        
        Args:
            root_node: ドラッグするルートノード
        """
        self._subtree_drag_mode = True
        self._subtree_drag_root = root_node
        self._subtree_drag_start_pos = root_node.pos()
        
        # 子孫ノードを取得
        descendants = self.get_descendants(root_node)
        
        # スナップショットを作成
        self._subtree_drag_snapshot = {}
        self._subtree_drag_edges_snapshot = {}
        
        # ルートノードの位置を記録
        self._subtree_drag_snapshot[root_node] = root_node.pos()
        
        # 元の位置を保存（衝突時の復元用）
        self._subtree_drag_original_positions = {}
        self._subtree_drag_original_positions[root_node] = root_node.pos()
        
        # 子孫ノードの位置を記録
        for descendant in descendants:
            self._subtree_drag_snapshot[descendant] = descendant.pos()
            self._subtree_drag_original_positions[descendant] = descendant.pos()
        
        # サブツリー内の接続線の制御点を記録
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source == root_node or connection.source in descendants or
                 connection.target == root_node or connection.target in descendants)):
                # 接続線の制御点を記録（CrankConnectionの場合は各線分の位置）
                if hasattr(connection, 'horizontal_line1') and hasattr(connection, 'vertical_line') and hasattr(connection, 'horizontal_line2'):
                    self._subtree_drag_edges_snapshot[connection] = {
                        'h1_start': connection.horizontal_line1.line().p1(),
                        'h1_end': connection.horizontal_line1.line().p2(),
                        'v_start': connection.vertical_line.line().p1(),
                        'v_end': connection.vertical_line.line().p2(),
                        'h2_start': connection.horizontal_line2.line().p1(),
                        'h2_end': connection.horizontal_line2.line().p2()
                    }
        
        # サブツリー内のすべての接続線を更新（初期状態を確実にするため）
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source in self._subtree_drag_snapshot or 
                 connection.target in self._subtree_drag_snapshot)):
                # 接続線の更新メソッドを呼び出し
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
    
    def update_subtree_drag(self, dx: float, dy: float):
        """
        サブツリードラッグ中の位置更新
        
        Args:
            dx: X方向の移動量
            dy: Y方向の移動量
        """
        if not self._subtree_drag_mode:
            return
        
        # 各ノードの位置を更新
        for node, original_pos in self._subtree_drag_snapshot.items():
            new_pos = QPointF(original_pos.x() + dx, original_pos.y() + dy)
            node.setPos(new_pos)
        
        # 接続線の制御点を更新
        for connection, original_points in self._subtree_drag_edges_snapshot.items():
            if hasattr(connection, 'horizontal_line1') and hasattr(connection, 'vertical_line') and hasattr(connection, 'horizontal_line2'):
                # 各線分の制御点を平行移動
                h1_start = QPointF(original_points['h1_start'].x() + dx, original_points['h1_start'].y() + dy)
                h1_end = QPointF(original_points['h1_end'].x() + dx, original_points['h1_end'].y() + dy)
                v_start = QPointF(original_points['v_start'].x() + dx, original_points['v_start'].y() + dy)
                v_end = QPointF(original_points['v_end'].x() + dx, original_points['v_end'].y() + dy)
                h2_start = QPointF(original_points['h2_start'].x() + dx, original_points['h2_start'].y() + dy)
                h2_end = QPointF(original_points['h2_end'].x() + dx, original_points['h2_end'].y() + dy)
                
                # 線分を更新
                connection.horizontal_line1.setLine(h1_start.x(), h1_start.y(), h1_end.x(), h1_end.y())
                connection.vertical_line.setLine(v_start.x(), v_start.y(), v_end.x(), v_end.y())
                connection.horizontal_line2.setLine(h2_start.x(), h2_start.y(), h2_end.x(), h2_end.y())
        
        # サブツリー内のすべての接続線を更新（移動中のノードとその親ノードを繋ぐ接続線を含む）
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source in self._subtree_drag_snapshot or 
                 connection.target in self._subtree_drag_snapshot)):
                # 接続線の更新メソッドを呼び出し
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        
        # シーンの再描画を強制
        self.scene.update()
    
    def end_subtree_drag(self, apply_snap: bool = True):
        """
        サブツリードラッグを終了
        
        Args:
            apply_snap: グリッドスナップを適用するかどうか
        """
        if not self._subtree_drag_mode:
            return
        
        # グリッドスナップが有効な場合
        if apply_snap and self.get_grid_snap_enabled():
            # ルートノードの位置をスナップ
            original_root_pos = self._subtree_drag_snapshot[self._subtree_drag_root]
            current_root_pos = self._subtree_drag_root.pos()
            snapped_root_pos = self.snap_to_grid(current_root_pos)
            
            # 最終的な移動量を再計算
            final_dx = snapped_root_pos.x() - original_root_pos.x()
            final_dy = snapped_root_pos.y() - original_root_pos.y()
            
            # 全ノードと接続線に最終移動量を適用
            self.update_subtree_drag(final_dx, final_dy)
        
        # Undoスタックに追加
        if self.undo_stack is not None:
            # 移動前後の位置を記録
            old_positions = {}
            new_positions = {}
            
            for node, original_pos in self._subtree_drag_snapshot.items():
                old_positions[node] = original_pos
                new_positions[node] = node.pos()
            
            # Undoコマンドを追加
            self.undo_stack.push(SubtreeMoveCommand(self, self._subtree_drag_root, old_positions, new_positions, self._subtree_drag_edges_snapshot))
        
        # サブツリー内のすべての接続線を最終更新
        for connection in self.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source in self._subtree_drag_snapshot or 
                 connection.target in self._subtree_drag_snapshot)):
                # 接続線の更新メソッドを呼び出し
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        
        # 状態をクリア
        self._subtree_drag_mode = False
        self._subtree_drag_root = None
        self._subtree_drag_start_pos = None
        self._subtree_drag_snapshot.clear()
        self._subtree_drag_edges_snapshot.clear()
        
        # レイアウトの再計算と再描画
        self.relayout()
    
    
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
    
    def check_collision(self, bbox: dict, exclude_node: NodeItem = None) -> bool:
        """
        指定された境界ボックスが他のノードと衝突するかチェック
        
        Args:
            bbox: チェックする境界ボックス {x, y, width, height, bottom}
            exclude_node: 衝突チェックから除外するノード
            
        Returns:
            bool: 衝突がある場合True
        """
        return self._check_collision(bbox, exclude_node)
    
    def push_down_until_no_collision(self, bbox: dict, step: float = None, exclude_node: NodeItem = None) -> dict:
        """
        衝突がなくなるまで下方向にプッシュ
        
        Args:
            bbox: プッシュする境界ボックス
            step: プッシュするステップサイズ（デフォルト: VERTICAL_GAP）
            exclude_node: 衝突チェックから除外するノード
            
        Returns:
            dict: プッシュ後の境界ボックス
        """
        if step is None:
            step = self.VERTICAL_GAP
        
        original_bbox = bbox.copy()
        
        while self._check_collision(bbox, exclude_node):
            bbox["y"] += step
            bbox["bottom"] = bbox["y"] + bbox["height"]
        
        return bbox
    
    def _push_down_until_no_collision(self, bbox: dict, step: float = 40.0, exclude_node: NodeItem = None) -> dict:
        """後方互換性のためのエイリアス"""
        return self.push_down_until_no_collision(bbox, step, exclude_node)
    
    def calculate_parent_insert_position(self, reference_parent: NodeItem) -> QPointF:
        """
        新しい親ノードの挿入位置を計算
        
        要求仕様:
        - Parent1の子ノード群の最下端 + 余白 に Parent2を配置
        - 既存ノードとの衝突回避
        - グリッドスナップ対応
        
        Args:
            reference_parent: 参照親ノード（Parent1）
            
        Returns:
            QPointF: 新しい親ノードの配置位置
        """
        # すべての既存の親ノードを取得
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        all_parent_nodes = self._get_all_parent_nodes(all_nodes)
        
        # すべての親ノードのサブツリーの最下端を計算
        max_bottom_y = reference_parent.pos().y()  # 初期値は参照親ノードのY座標
        for parent in all_parent_nodes:
            subtree_bbox = self.get_subtree_bbox(parent, True)
            max_bottom_y = max(max_bottom_y, subtree_bbox["bottom"])
        
        # 新しい親ノードの配置位置を計算
        # X座標: 既存の親ノード列のX位置（Parent1と同じ列 or 右の親列）
        new_parent_x = reference_parent.pos().x() + self.PARENT_COLUMN_OFFSET
        
        # Y座標: すべての親ノードのサブツリーの最下端 + 垂直ギャップ
        new_parent_y = max_bottom_y + self.VERTICAL_GAP
        
        # 新しい親ノードの境界ボックスを作成
        new_parent_bbox = {
            "x": new_parent_x,
            "y": new_parent_y,
            "width": self.NODE_WIDTH,
            "height": self.NODE_HEIGHT,
            "bottom": new_parent_y + self.NODE_HEIGHT
        }
        
        # 既存ノードとの衝突回避
        final_bbox = self.push_down_until_no_collision(new_parent_bbox)
        
        # グリッドスナップが有効な場合は適用
        if self.get_grid_snap_enabled():
            snapped_pos = self.snap_to_grid(QPointF(final_bbox["x"], final_bbox["y"]))
            return snapped_pos
        
        return QPointF(final_bbox["x"], final_bbox["y"])
    
    def _calculate_parent_insert_position(self, reference_parent: NodeItem) -> QPointF:
        """後方互換性のためのエイリアス"""
        return self.calculate_parent_insert_position(reference_parent)
    
    def relayout(self):
        """
        レイアウトの再計算と再描画
        
        ノード追加・移動後にコネクタの再計算と再描画を行う
        """
        # すべての接続線を更新
        for connection in self.connections:
            if hasattr(connection, 'update_connection'):
                connection.update_connection()
        
        # シーンの再描画
        self.scene.update()
        
        # オートフィットが有効な場合は自動的にフィット
        if self.auto_fit_enabled:
            self.fit_all_nodes()
    
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
    
    def _check_node_collision(self, node: 'NodeItem', target_pos: QPointF) -> bool:
        """ノードの衝突をチェック"""
        target_rect = QRectF(target_pos.x() - node.boundingRect().width()/2,
                           target_pos.y() - node.boundingRect().height()/2,
                           node.boundingRect().width(),
                           node.boundingRect().height())

        # 他のノードとの衝突チェック（ノード同士の重なりを防ぐ）
        for item in self.scene.items():
            if isinstance(item, NodeItem) and item != node:
                item_rect = item.sceneBoundingRect()
                # ノード同士の重なりを防ぐための弾き幅
                margin = 5  # 弾き幅=5px
                expanded_rect = QRectF(item_rect.x() - margin, item_rect.y() - margin,
                                     item_rect.width() + 2*margin, item_rect.height() + 2*margin)
                if target_rect.intersects(expanded_rect):
                    return True
        
        # 自身の接続線（縦線）上への配置を禁止（X軸方向のみ判定）
        if self._check_own_vertical_line_overlap(node, target_rect):
            return True

        # 接続線との一般的な衝突チェックは無効化（Y軸方向の移動を自由にするため）
        return False

    def _check_own_vertical_line_overlap(self, node: 'NodeItem', target_rect: QRectF) -> bool:
        """自身に接続しているCrankConnectionのvertical_line上に重なるか（X軸のみ）"""
        try:
            margin = 3  # 最小限の許容幅
            for connection in self.connections:
                if not (hasattr(connection, 'source') and hasattr(connection, 'target')):
                    continue
                if connection.source is not node and connection.target is not node:
                    continue
                if not hasattr(connection, 'vertical_line') or not connection.vertical_line:
                    continue
                line = connection.vertical_line.line()
                line_x = line.x1()
                # ノード矩形が縦線のX位置に被っているか（Y方向は自由）
                if (target_rect.left() <= line_x + margin and
                    target_rect.right() >= line_x - margin):
                    return True
            return False
        except Exception as e:
            print(f"_check_own_vertical_line_overlap エラー: {e}")
            return False

    def _check_insertion_zone(self, dragged_node: 'NodeItem', target_pos: QPointF) -> tuple[bool, 'NodeItem', int]:
        """挿入ゾーンの検出（親ノードの15px以内）"""
        try:
            from node import NodeItem
            insertion_threshold = 15.0  # 15px以内
            
            for item in self.scene.items():
                if isinstance(item, NodeItem) and item != dragged_node:
                    # ドラッグ中のノードがこのノードの子かどうかチェック
                    is_child = False
                    for connection in self.connections:
                        if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                            connection.source == item and connection.target == dragged_node):
                            is_child = True
                            break
                    
                    if is_child:
                        # 親ノードの位置を取得
                        parent_rect = item.sceneBoundingRect()
                        parent_center = parent_rect.center()
                        
                        # 距離を計算
                        distance = ((target_pos.x() - parent_center.x()) ** 2 + 
                                   (target_pos.y() - parent_center.y()) ** 2) ** 0.5
                        
                        if distance <= insertion_threshold:
                            # 挿入位置を計算（Y座標ベース）
                            child_nodes = []
                            for conn in self.connections:
                                if (hasattr(conn, 'source') and hasattr(conn, 'target') and
                                    conn.source == item):
                                    child_nodes.append(conn.target)
                            
                            # Y座標でソート
                            child_nodes.sort(key=lambda n: n.pos().y())
                            
                            # 挿入位置を決定
                            insert_index = 0
                            for i, child in enumerate(child_nodes):
                                if child == dragged_node:
                                    continue
                                if target_pos.y() < child.pos().y():
                                    insert_index = i
                                    break
                                insert_index = i + 1
                            
                            return True, item, insert_index
            
            return False, None, 0
        except Exception as e:
            print(f"_check_insertion_zone エラー: {e}")
            return False, None, 0

    def _reorder_child_nodes(self, parent_node: 'NodeItem', dragged_node: 'NodeItem', insert_index: int):
        """子ノードの順番を変更"""
        try:
            # 既存の接続を削除
            connections_to_remove = []
            for connection in self.connections:
                if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                    connection.source == parent_node and connection.target == dragged_node):
                    connections_to_remove.append(connection)
            
            for conn in connections_to_remove:
                self._remove_connection(conn)
            
            # 他の子ノードの位置を調整
            child_nodes = []
            for conn in self.connections:
                if (hasattr(conn, 'source') and hasattr(conn, 'target') and
                    conn.source == parent_node):
                    child_nodes.append(conn.target)
            
            # ドラッグされたノードを除外
            child_nodes = [n for n in child_nodes if n != dragged_node]
            
            # 挿入位置にドラッグされたノードを挿入
            child_nodes.insert(insert_index, dragged_node)
            
            # 新しい接続を作成
            self._create_edge(parent_node, dragged_node)
            
            # 子ノードの位置を再配置
            self._reposition_child_nodes(parent_node, child_nodes)
            
        except Exception as e:
            print(f"_reorder_child_nodes エラー: {e}")

    def _reposition_child_nodes(self, parent_node: 'NodeItem', child_nodes: list):
        """子ノードの位置を再配置"""
        try:
            parent_rect = parent_node.sceneBoundingRect()
            start_x = parent_rect.right() + 40  # 親ノードから40px右
            start_y = parent_rect.center().y()
            
            # 子ノードを縦に配置
            for i, child in enumerate(child_nodes):
                new_y = start_y + (i - len(child_nodes) // 2) * 80  # 80px間隔
                child.setPos(start_x, new_y)
            
            # 接続線を更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
                    
        except Exception as e:
            print(f"_reposition_child_nodes エラー: {e}")
    
    def _check_lane_insertion(self, dragged_node: 'NodeItem', target_pos: QPointF) -> tuple[bool, list, int]:
        """縦レーン内への割り込み挿入を判定（親距離を使わない）
        Returns: (should_insert, lane_nodes, insert_index)
        """
        try:
            from node import NodeItem
            lane_width = 60.0  # ドロップX±lane_width内を同じ縦レーンとみなす
            candidates = [item for item in self.scene.items() if isinstance(item, NodeItem) and item is not dragged_node]
            if not candidates:
                return False, [], 0
            lane_nodes = [n for n in candidates if abs(n.pos().x() - target_pos.x()) <= lane_width]
            if not lane_nodes:
                return False, [], 0
            lane_nodes.sort(key=lambda n: n.pos().y())
            if len(lane_nodes) == 1:
                insert_index = 0 if target_pos.y() <= lane_nodes[0].pos().y() else 1
                return True, lane_nodes, insert_index
            midpoints = []
            for i in range(len(lane_nodes) - 1):
                midpoints.append((lane_nodes[i].pos().y() + lane_nodes[i+1].pos().y()) / 2.0)
            if target_pos.y() < midpoints[0]:
                return True, lane_nodes, 0
            for i in range(len(midpoints)-1):
                if midpoints[i] <= target_pos.y() < midpoints[i+1]:
                    return True, lane_nodes, i+1
            return True, lane_nodes, len(lane_nodes)
        except Exception as e:
            print(f"_check_lane_insertion エラー: {e}")
            return False, [], 0

    def _reposition_lane_nodes(self, lane_nodes_with_dragged: list['NodeItem']) -> None:
        """縦レーンのノード群を必要最小限だけ下に押し下げて非重なり化（最小ギャップ=5px、Xは維持）。

        等間隔で広げず、先頭ノードのYをアンカーにし、以降のノードは
        直前ノードの下端+最小ギャップを下回るときだけ下方向へ補正します。
        これにより「割り込み」と「寄せ」を両立します。
        """
        try:
            if not lane_nodes_with_dragged:
                return
            # Y昇順に並び替え（先頭＝最上位ノード）
            lane_nodes_with_dragged.sort(key=lambda n: n.pos().y())

            min_gap = 5.0

            # 先頭ノードはそのまま（必要ならドラッグにより既に近接している前提）
            first = lane_nodes_with_dragged[0]
            prev_center_y = first.pos().y()
            prev_h = first.boundingRect().height()
            prev_bottom = prev_center_y + prev_h / 2.0

            # 2番目以降：必要最小限の下方向補正のみ行う
            for n in lane_nodes_with_dragged[1:]:
                cur_center_y = n.pos().y()
                cur_h = n.boundingRect().height()
                cur_top = cur_center_y - cur_h / 2.0

                required_top = prev_bottom + min_gap
                # 要求上端より上にある場合のみ押し下げる（上方向への引き寄せは維持）
                if cur_top < required_top:
                    dy = (required_top - cur_top)
                    self._translate_subtree_vertical(n, dy)
                    # 補正後に中心Yを更新
                    cur_center_y = n.pos().y()
                    cur_top = cur_center_y - cur_h / 2.0

                # 次の比較用に更新
                prev_bottom = cur_top + cur_h

            # 接続線更新とシーン更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
            self.scene.update()

            # サブツリー間の最小ギャップも5pxで正規化（必要最小限の下方向補正のみ）
            self._normalize_subtree_spacing(lane_nodes_with_dragged, min_gap=min_gap)
        except Exception as e:
            print(f"_reposition_lane_nodes エラー: {e}")

    def _translate_subtree_vertical(self, root: 'NodeItem', dy: float) -> None:
        """rootノードとその子孫ノードをY方向にdyだけ平行移動する。接続線も更新。"""
        try:
            # 対象ノード集合を作成
            nodes_to_move = [root]
            if hasattr(self, 'get_descendants'):
                try:
                    nodes_to_move.extend(self.get_descendants(root))
                except Exception:
                    pass
            # 位置更新（Xは据え置き）
            for node in nodes_to_move:
                pos = node.pos()
                node.setPos(pos.x(), pos.y() + dy)
            # 接続線更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        except Exception as e:
            print(f"_translate_subtree_vertical エラー: {e}")

    def _normalize_subtree_spacing(self, ordered_parents: list['NodeItem'], min_gap: float = 20.0) -> None:
        """Y昇順の親リストについて、各サブツリーの下端と次サブツリー上端の間をmin_gapに揃える（不足分のみ下方へ）。"""
        try:
            if not ordered_parents:
                return
            # 先頭のサブツリー境界
            prev_bbox = self.get_subtree_bbox(ordered_parents[0], include_descendants=True)
            # 下方向だけ補正: gap < min_gap のときだけ押し下げる。gap > min_gap の場合は何もしない（寄せはユーザのドラッグで行える）
            for parent in ordered_parents[1:]:
                bbox = self.get_subtree_bbox(parent, include_descendants=True)
                gap = bbox["y"] - prev_bbox["bottom"]
                if gap < min_gap:
                    dy = (prev_bbox["bottom"] + min_gap) - bbox["y"]
                    self._translate_subtree_vertical(parent, dy)
                    # 押し下げ後の境界を再取得
                    bbox = self.get_subtree_bbox(parent, include_descendants=True)
                # 次ループ用に前のボックスを更新
                prev_bbox = {"y": prev_bbox["y"], "bottom": bbox["bottom"]}
            # 最後に接続線とシーン更新
            for connection in self.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
            self.scene.update()
        except Exception as e:
            print(f"_resolve_subtree_overlaps エラー: {e}")

    

    def _check_connection_line_collision(self, node: 'NodeItem', target_rect: QRectF) -> bool:
        """接続線との衝突をチェック（X軸方向のみ、Y軸方向は完全に自由）"""
        for connection in self.connections:
            if hasattr(connection, 'vertical_line') and connection.vertical_line:
                # 垂直線の位置を取得
                line = connection.vertical_line.line()
                # X軸方向のみの衝突チェック（Y軸方向は完全に自由）
                margin = 1  # X軸方向のマージンを最小限に
                line_x = line.x1()
                
                # ノードが垂直線のX軸位置と重なる場合のみ衝突とみなす
                # Y軸方向の重なりは完全に無視
                if (target_rect.left() <= line_x + margin and 
                    target_rect.right() >= line_x - margin):
                    return True
                    
            # horizontal_line2との衝突もチェック（X軸方向のみ）
            if hasattr(connection, 'horizontal_line2') and connection.horizontal_line2:
                line2 = connection.horizontal_line2.line()
                # X軸方向のみの衝突チェック
                margin = 1
                line2_x_start = min(line2.x1(), line2.x2())
                line2_x_end = max(line2.x1(), line2.x2())
                
                # ノードが水平線2のX軸範囲と重なる場合のみ衝突とみなす
                # Y軸方向の重なりは完全に無視
                if (target_rect.left() <= line2_x_end + margin and 
                    target_rect.right() >= line2_x_start - margin):
                    return True
        return False

    def _check_subtree_collision(self, root_node: 'NodeItem') -> bool:
        """サブツリー（ルート＋子孫）いずれかが他ノードに重なるかチェック"""
        try:
            # サブツリー対象ノード集合
            subtree_nodes = [root_node]
            for n in self.get_descendants(root_node):
                subtree_nodes.append(n)

            # 各サブツリーノードの現在矩形
            current_rects = {
                n: QRectF(
                    n.pos().x() - n.boundingRect().width() / 2.0,
                    n.pos().y() - n.boundingRect().height() / 2.0,
                    n.boundingRect().width(),
                    n.boundingRect().height(),
                ) for n in subtree_nodes
            }

            # 他ノードとの衝突検出の弾き幅
            margin = 5
            for item in self.scene.items():
                from node import NodeItem  # 遅延インポート
                if isinstance(item, NodeItem) and item not in subtree_nodes:
                    item_rect = item.sceneBoundingRect()
                    expanded_rect = QRectF(
                        item_rect.x() - margin,
                        item_rect.y() - margin,
                        item_rect.width() + 2 * margin,
                        item_rect.height() + 2 * margin,
                    )
                    # サブツリーノードのいずれかが重なれば衝突
                    for n, r in current_rects.items():
                        if r.intersects(expanded_rect):
                            return True
            return False
        except Exception as e:
            print(f"_check_subtree_collision エラー: {e}")
            return False
