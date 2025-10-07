import sys
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QPen,
    QAction,
    QPainter,
    QUndoStack,
    QUndoCommand,
    QKeySequence,
    QColor,
    QTransform,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMainWindow,
    QToolBar,
    QInputDialog,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QSlider,
    QLabel,
    QHBoxLayout,
    QWidget,
    QDialog,
    QVBoxLayout,
    QPushButton,
)


class CrankConnection:
    """3段階クランク状の接続線を管理するクラス（水平→垂直→水平）"""
    def __init__(self, scene: QGraphicsScene, source: 'NodeItem', target: 'NodeItem'):
        self.scene = scene
        self.source = source
        self.target = target
        self.horizontal_line1: QGraphicsLineItem | None = None  # 最初の水平線
        self.vertical_line: QGraphicsLineItem | None = None      # 垂直線
        self.horizontal_line2: QGraphicsLineItem | None = None  # 2番目の水平線
        self._create_crank_lines()
    
    def _create_crank_lines(self):
        """3段階クランク状の線を作成"""
        pen = QPen(Qt.darkGray, 1.0)  # より細い線
        pen.setStyle(Qt.DashLine)     # 破線スタイル
        
        # 最初の水平線
        self.horizontal_line1 = self.scene.addLine(0, 0, 0, 0, pen)
        self.horizontal_line1.setZValue(-1)
        
        # 垂直線
        self.vertical_line = self.scene.addLine(0, 0, 0, 0, pen)
        self.vertical_line.setZValue(-1)
        
        # 2番目の水平線
        self.horizontal_line2 = self.scene.addLine(0, 0, 0, 0, pen)
        self.horizontal_line2.setZValue(-1)
        
        # 接続線の透明度を設定（MindMapViewから取得）
        if hasattr(self.source, '_view') and hasattr(self.source._view, 'line_transparency'):
            line_transparency = self.source._view.line_transparency
            self.horizontal_line1.setOpacity(line_transparency)
            self.vertical_line.setOpacity(line_transparency)
            self.horizontal_line2.setOpacity(line_transparency)
    
    def update_connection(self):
        """接続線の位置を更新"""
        if not self.horizontal_line1 or not self.vertical_line or not self.horizontal_line2:
            return
            
        # ノードの境界矩形を取得
        source_rect = self.source.sceneBoundingRect()
        target_rect = self.target.sceneBoundingRect()
        
        # 接続点を計算
        if source_rect.center().x() < target_rect.center().x():
            # 左から右への接続
            start_x = source_rect.right()
            start_y = source_rect.center().y()
            end_x = target_rect.left()
            end_y = target_rect.center().y()
        else:
            # 右から左への接続
            start_x = source_rect.left()
            start_y = source_rect.center().y()
            end_x = target_rect.right()
            end_y = target_rect.center().y()
        
        # 階層レベルに基づいて垂直線のX位置を統一
        vertical_x = self._get_unified_vertical_x_position()
        
        # 最初の水平線（開始点から垂直線の位置まで）
        self.horizontal_line1.setLine(start_x, start_y, vertical_x, start_y)
        
        # 垂直線（統一されたX位置で描画）
        self.vertical_line.setLine(vertical_x, start_y, vertical_x, end_y)
        
        # 2番目の水平線（垂直線の位置から終了点まで）
        self.horizontal_line2.setLine(vertical_x, end_y, end_x, end_y)
    
    def _get_unified_vertical_x_position(self):
        """統一された垂直線のX位置を取得（全て基本位置+20）"""
        # 基本位置+20に統一
        base_x = self.source.sceneBoundingRect().right()
        vertical_x = base_x + 20
        
        return vertical_x
    
    
    def remove(self):
        """接続線を削除"""
        if self.horizontal_line1:
            self.scene.removeItem(self.horizontal_line1)
        if self.vertical_line:
            self.scene.removeItem(self.vertical_line)
        if self.horizontal_line2:
            self.scene.removeItem(self.horizontal_line2)


class NodeItem(QGraphicsRectItem):
    """シンプルなノード（四角形 + テキスト）。ドラッグ可能/選択可能。"""

    def __init__(self, view: 'MindMapView', label: str = "ノード", width: float = 128.0, height: float = 72.0):
        super().__init__(QRectF(-width / 2.0, -height / 2.0, width, height))
        self._view = view

        self.setBrush(QBrush(Qt.white))
        very_light_gray = QColor(200, 200, 200)  # より薄いグレー
        self.setPen(QPen(very_light_gray, 1.5))
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)

        self.text_item = QGraphicsTextItem(label, self)
        self.text_item.setDefaultTextColor(Qt.black)
        # 中央寄せ
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(-text_rect.width() / 2.0, -text_rect.height() / 2.0)

        # 接続エッジ参照（(connection, other_node) のタプル）
        self._edges: list[tuple['CrankConnection', 'NodeItem']] = []
        self._press_pos: QPointF | None = None
        self._is_editing = False
        self._line_edit: QLineEdit | None = None

    def attach_edge(self, connection: 'CrankConnection', other: 'NodeItem') -> None:
        self._edges.append((connection, other))
        # 追加時に一度更新
        self._update_attached_lines()

    def _update_attached_lines(self) -> None:
        for connection, other in self._edges:
            connection.update_connection()

    def itemChange(self, change: 'QGraphicsItem.GraphicsItemChange', value):  # type: ignore[override]
        # 位置変更時にリアルタイムグリッドスナップと衝突検出を適用
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
                    # スナップ後の位置でも衝突検出
                    if self._view._is_position_free_for_node(snapped_pos, self):
                        return snapped_pos
                    else:
                        # スナップ位置が衝突する場合は元の位置を返す
                        return self.pos()
                else:
                    # グリッドスナップがOFFの場合は衝突検出のみ
                    if self._view._is_position_free_for_node(value, self):
                        return value
                    else:
                        # 衝突する場合は元の位置を返す
                        return self.pos()
        
        # 位置変更後にライン更新
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._update_attached_lines()
            # 接続線の交差解決は手動実行のみに変更（無限ループを防ぐ）
            # self._view._resolve_connection_line_intersections()  # コメントアウト
        # 選択状態の変化を検知して枠線の太さを調整
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self._update_selection_style()
        return super().itemChange(change, value)

    def _update_selection_style(self):
        """選択状態に応じて枠線の太さと色を調整"""
        if self.isSelected():
            # 選択時は微細に太いグレーの枠線
            self.setPen(QPen(Qt.gray, 1.6))
        else:
            # 非選択時はさらに薄いグレーの枠線
            very_light_gray = QColor(200, 200, 200)  # より薄いグレー
            self.setPen(QPen(very_light_gray, 1.5))

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
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
            
            if move_distance > 5.0 and self._view.undo_stack is not None:  # 5ピクセル以上の移動
                # 単一ノード移動の処理
                if self._view._should_move_related_nodes(self, self.pos()):
                    # 重なる場合は関連ノードも移動
                    self._view.undo_stack.push(MoveNodeWithRelatedCommand(self._view, self, self._press_pos, self.pos()))
                else:
                    # 重ならない場合は単純な移動のみ
                    self._view.undo_stack.push(MoveNodeCommand(self, self._press_pos, self.pos()))
        self._press_pos = None
        return super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """ダブルクリックでインライン編集開始"""
        try:
            if not self._is_editing:
                self._start_safe_inline_editing()
        except Exception as e:
            print(f"ダブルクリック時のエラー: {e}")
            self._cleanup_editing()
        return super().mouseDoubleClickEvent(event)


    def _start_safe_inline_editing(self):
        """安全なインライン編集を開始"""
        if self._is_editing:
            return
        
        try:
            self._is_editing = True
            current_text = self.text_item.toPlainText()
            
            # テキストアイテムを非表示
            self.text_item.setVisible(False)
            
            # LineEditを作成
            self._line_edit = QLineEdit(current_text)
            self._line_edit.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #0078d4;
                    border-radius: 4px;
                    padding: 4px 8px;
                    background-color: white;
                    font-size: 12px;
                    min-width: 80px;
                }
            """)
            
            # ノードの位置をビュー座標に変換
            node_pos = self._view.mapFromScene(self.scenePos())
            text_rect = self.text_item.boundingRect()
            
            # LineEditのサイズを計算
            font_metrics = self._line_edit.fontMetrics()
            text_width = font_metrics.horizontalAdvance(current_text)
            edit_width = max(80, text_width + 20)
            edit_height = int(text_rect.height() + 8)
            
            # LineEditをビューの親ウィンドウに配置
            parent_widget = self._view.parent()
            if parent_widget:
                # ビュー座標を親ウィンドウ座標に変換
                global_pos = self._view.mapToGlobal(node_pos)
                parent_pos = parent_widget.mapFromGlobal(global_pos)
                
                self._line_edit.setParent(parent_widget)
                self._line_edit.setGeometry(
                    parent_pos.x() - edit_width // 2,
                    parent_pos.y() - edit_height // 2,
                    edit_width,
                    edit_height
                )
                self._line_edit.show()
                self._line_edit.setFocus()
                self._line_edit.selectAll()
                
                # イベントハンドラーを設定
                self._line_edit.returnPressed.connect(self._finish_editing)
                self._line_edit.focusOutEvent = self._line_edit_focus_out
                self._line_edit.keyPressEvent = self._line_edit_key_press
            else:
                # フォールバック: ダイアログを使用
                self._cleanup_editing()
                self._show_rename_dialog()
                
        except Exception as e:
            print(f"インライン編集開始時のエラー: {e}")
            self._cleanup_editing()

    def _show_rename_dialog(self):
        """リネームダイアログを表示（フォールバック）"""
        try:
            current_text = self.text_item.toPlainText()
            new_text, ok = QInputDialog.getText(
                self._view, 
                "ノード名変更", 
                "新しいノード名:", 
                text=current_text
            )
            if ok and new_text.strip() and new_text != current_text:
                if self._view.undo_stack is not None:
                    self._view.undo_stack.push(RenameNodeCommand(self, current_text, new_text.strip()))
                else:
                    self._rename_node(new_text.strip())
        except Exception as e:
            print(f"ダイアログ表示時のエラー: {e}")

    def _line_edit_focus_out(self, event):
        """LineEditのフォーカスアウト時の処理"""
        self._finish_editing()
        QLineEdit.focusOutEvent(self._line_edit, event)

    def _line_edit_key_press(self, event):
        """LineEditのキーイベント処理"""
        from PySide6.QtCore import Qt
        if event.key() == Qt.Key_Escape:
            self._cancel_editing()
            return
        QLineEdit.keyPressEvent(self._line_edit, event)

    def _finish_editing(self):
        """編集を終了"""
        if not self._is_editing or not self._line_edit:
            return
        
        try:
            new_text = self._line_edit.text().strip()
            current_text = self.text_item.toPlainText()
            
            self._cleanup_editing()
            
            # テキストが変更された場合のみ更新
            if new_text and new_text != current_text:
                if self._view.undo_stack is not None:
                    self._view.undo_stack.push(RenameNodeCommand(self, current_text, new_text))
                else:
                    self._rename_node(new_text)
        except Exception as e:
            print(f"編集終了時のエラー: {e}")
            self._cleanup_editing()

    def _cancel_editing(self):
        """編集をキャンセル"""
        self._cleanup_editing()

    def _cleanup_editing(self):
        """編集状態をクリーンアップ"""
        self._is_editing = False
        
        if self._line_edit:
            try:
                self._line_edit.hide()
                self._line_edit.deleteLater()
            except:
                pass
            self._line_edit = None
        
        # テキストアイテムを再表示
        self.text_item.setVisible(True)

    def _rename_node(self, new_text: str):
        """ノード名を変更"""
        self.text_item.setPlainText(new_text)
        # テキストを中央寄せ
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(-text_rect.width() / 2.0, -text_rect.height() / 2.0)


class MindMapView(QGraphicsView):
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
        
        # ズームスピードのパラメータ
        self.zoom_speed = 1.15  # デフォルトのズームスピード（1.15倍）
        
        # 透明度のパラメータ
        self.background_transparency = 1.0  # 背景透明度（デフォルト不透明）
        self.node_transparency = 1.0        # ノード透明度（デフォルト不透明）
        self.line_transparency = 1.0        # 接続線透明度（デフォルト不透明）
        
        # グリッドのパラメータ
        self.grid_enabled = False           # グリッド表示（デフォルトOFF）
        self.grid_size = 20                 # グリッドサイズ（ピクセル）
        self.grid_snap_enabled = False      # グリッドスナップ（デフォルトOFF）
        
        # 複数ノード選択時の移動用
        self._multi_move_start_positions: dict[NodeItem, QPointF] = {}
        self._is_multi_move_in_progress = False

    def add_node(self, label: str = "ノード", pos: QPointF | None = None, is_parent_node: bool = False) -> NodeItem:
        node = NodeItem(self, label)
        if pos is None:
            if is_parent_node:
                # 親ノードの場合は適切な位置を計算
                pos = self._calculate_parent_node_position()
            else:
                # 子ノードの場合は中央に配置
                pos = self.mapToScene(self.viewport().rect().center())
        
        # 位置が指定されている場合は衝突検出を実行
        if pos is not None:
            all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
            pos = self._find_collision_free_position(pos, all_nodes)
        
        node.setPos(pos)
        # ノードの透明度を設定
        node.setOpacity(self.node_transparency)
        self.scene.addItem(node)
        return node

    def wheelEvent(self, event):
        # マウスホイールでズーム（ズームスピードパラメータを使用）
        zoom_in_factor = self.zoom_speed
        zoom_out_factor = 1.0 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def set_zoom_speed(self, speed: float):
        """ズームスピードを設定（1.0より大きい値）"""
        if speed > 1.0:
            self.zoom_speed = speed
        else:
            print("ズームスピードは1.0より大きい値である必要があります")

    def get_zoom_speed(self) -> float:
        """現在のズームスピードを取得"""
        return self.zoom_speed

    def set_background_transparency(self, transparency: float):
        """背景透明度を設定（0.0-1.0）"""
        if 0.0 <= transparency <= 1.0:
            self.background_transparency = transparency
            # シーンの背景色を透明に設定
            if transparency == 0.0:
                # 完全透明の場合
                self.scene.setBackgroundBrush(QBrush(Qt.transparent))
                # 複数の方法で背景を透明化
                self.setStyleSheet("""
                    QGraphicsView { 
                        background: transparent; 
                        border: none; 
                    }
                    QGraphicsView::viewport {
                        background: transparent;
                    }
                """)
                # 透明化属性を設定
                self.setAttribute(Qt.WA_TranslucentBackground, True)
                self.setAttribute(Qt.WA_NoSystemBackground, True)
                # 親ウィンドウも透明化
                if hasattr(self.parent(), 'setAttribute'):
                    self.parent().setAttribute(Qt.WA_TranslucentBackground, True)
                    self.parent().setAttribute(Qt.WA_NoSystemBackground, True)
            else:
                # 半透明の場合
                bg_color = QColor(255, 255, 255, int(255 * transparency))
                self.scene.setBackgroundBrush(QBrush(bg_color))
                self.setStyleSheet(f"""
                    QGraphicsView {{ 
                        background: rgba(255, 255, 255, {int(255 * transparency)}); 
                        border: none; 
                    }}
                    QGraphicsView::viewport {{
                        background: rgba(255, 255, 255, {int(255 * transparency)});
                    }}
                """)
                # 通常の背景設定に戻す
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                self.setAttribute(Qt.WA_NoSystemBackground, False)
                if hasattr(self.parent(), 'setAttribute'):
                    self.parent().setAttribute(Qt.WA_TranslucentBackground, False)
                    self.parent().setAttribute(Qt.WA_NoSystemBackground, False)
        else:
            print("背景透明度は0.0から1.0の範囲で設定してください")

    def set_node_transparency(self, transparency: float):
        """ノード透明度を設定（0.1-1.0）"""
        if 0.1 <= transparency <= 1.0:
            self.node_transparency = transparency
            # 既存のノードの透明度を更新
            for item in self.scene.items():
                if isinstance(item, NodeItem):
                    item.setOpacity(transparency)
        else:
            print("ノード透明度は0.1から1.0の範囲で設定してください")

    def set_line_transparency(self, transparency: float):
        """接続線透明度を設定（0.1-1.0）"""
        if 0.1 <= transparency <= 1.0:
            self.line_transparency = transparency
            # 既存の接続線の透明度を更新
            for item in self.scene.items():
                if isinstance(item, QGraphicsLineItem):
                    item.setOpacity(transparency)
        else:
            print("接続線透明度は0.1から1.0の範囲で設定してください")

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
    
    def _update_grid_display(self):
        """グリッド表示を更新"""
        if self.grid_enabled:
            # グリッドを表示
            self.scene.setBackgroundBrush(self._create_grid_brush())
        else:
            # グリッドを非表示（背景透明化設定に従う）
            if self.background_transparency == 0.0:
                self.scene.setBackgroundBrush(QBrush(Qt.transparent))
            else:
                bg_color = QColor(255, 255, 255, int(255 * self.background_transparency))
                self.scene.setBackgroundBrush(QBrush(bg_color))
    
    def _create_grid_brush(self):
        """グリッドパターンのブラシを作成"""
        # グリッド用の画像を作成
        grid_image = QPixmap(self.grid_size, self.grid_size)
        grid_image.fill(Qt.transparent)
        
        painter = QPainter(grid_image)
        painter.setPen(QPen(QColor(200, 200, 200, 100), 1))
        
        # グリッド線を描画
        painter.drawLine(0, 0, self.grid_size, 0)  # 上線
        painter.drawLine(0, 0, 0, self.grid_size)  # 左線
        
        painter.end()
        
        # パターンブラシを作成
        brush = QBrush(grid_image)
        brush.setTransform(QTransform.fromScale(1, 1))
        return brush
    
    def snap_to_grid(self, pos: QPointF) -> QPointF:
        """位置をグリッドにスナップ"""
        if not self.grid_snap_enabled:
            return pos
        
        # グリッドサイズで丸める
        x = round(pos.x() / self.grid_size) * self.grid_size
        y = round(pos.y() / self.grid_size) * self.grid_size
        return QPointF(x, y)
    
    def _navigate_to_nearest_node(self, direction: Qt.Key):
        """カーソルキーで最寄りのノードに選択を移動"""
        # 現在選択されているノードを取得
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            # 選択されているノードがない場合は最初のノードを選択
            all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
            if all_nodes:
                all_nodes[0].setSelected(True)
            return
        
        current_node = selected_nodes[0]  # 最初の選択ノードを基準とする
        current_pos = current_node.pos()
        
        # 全てのノードを取得
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        if len(all_nodes) <= 1:
            return  # ノードが1個以下なら移動できない
        
        # 方向に応じて最寄りのノードを検索
        nearest_node = None
        min_distance = float('inf')
        
        for node in all_nodes:
            if node == current_node:
                continue  # 現在のノードは除外
            
            node_pos = node.pos()
            dx = node_pos.x() - current_pos.x()
            dy = node_pos.y() - current_pos.y()
            
            # 方向に応じて候補を絞る
            is_candidate = False
            distance = 0
            
            if direction == Qt.Key_Up:
                # 上方向: Y座標が小さい（上にある）ノード
                if dy < 0:
                    is_candidate = True
                    distance = abs(dy) + abs(dx) * 0.1  # 垂直距離を重視
            elif direction == Qt.Key_Down:
                # 下方向: Y座標が大きい（下にある）ノード
                if dy > 0:
                    is_candidate = True
                    distance = abs(dy) + abs(dx) * 0.1  # 垂直距離を重視
            elif direction == Qt.Key_Left:
                # 左方向: X座標が小さい（左にある）ノード
                if dx < 0:
                    is_candidate = True
                    distance = abs(dx) + abs(dy) * 0.1  # 水平距離を重視
            elif direction == Qt.Key_Right:
                # 右方向: X座標が大きい（右にある）ノード
                if dx > 0:
                    is_candidate = True
                    distance = abs(dx) + abs(dy) * 0.1  # 水平距離を重視
            
            if is_candidate and distance < min_distance:
                min_distance = distance
                nearest_node = node
        
        # 最寄りのノードが見つかった場合は選択を移動
        if nearest_node:
            # 現在の選択を解除
            current_node.setSelected(False)
            # 新しいノードを選択
            nearest_node.setSelected(True)
            
            # 選択されたノードが画面内に表示されるようスクロール
            self.ensureVisible(nearest_node)
    

    def fit_all_nodes(self) -> None:
        """全ノードが画面に収まるようズーム・パン"""
        items = [it for it in self.scene.items() if isinstance(it, NodeItem)]
        if not items:
            return

        # ノードの境界矩形を計算
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())

        # マージンを追加（境界ぎりぎりではなく余裕を持たせる）
        margin = 50
        rect.adjust(-margin, -margin, margin, margin)

        # ビューポートにフィット
        self.fitInView(rect, Qt.KeepAspectRatio)

    def mousePressEvent(self, event):
        # 複数ノード選択時の移動開始位置を記録
        if event.button() == Qt.LeftButton:
            selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
            if len(selected_nodes) > 1:
                # 複数ノードが選択されている場合、各ノードの開始位置を記録
                self._multi_move_start_positions.clear()
                self._is_multi_move_in_progress = True
                for node in selected_nodes:
                    self._multi_move_start_positions[node] = node.pos()
        
        # Shiftキーを押しながらのクリックでのみ接続モードを有効にする
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier:
            clicked_item = self.itemAt(event.pos())
            if isinstance(clicked_item, NodeItem):
                if self.pending_source_node is None:
                    # 1つ目のノード選択
                    self.pending_source_node = clicked_item
                    clicked_item.setSelected(True)  # 視覚的フィードバック
                else:
                    # 2つ目のノードでエッジ作成
                    if clicked_item is not self.pending_source_node:
                        if self.undo_stack is not None:
                            self.undo_stack.push(ConnectNodesCommand(self, self.pending_source_node, clicked_item))
                        else:
                            self._create_edge(self.pending_source_node, clicked_item)
                    # 接続完了後、選択状態をクリア
                    self.pending_source_node.setSelected(False)
                    self.pending_source_node = None
                return  # 接続モードではここで処理終了
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 複数ノード移動中の状態を更新
        if self._is_multi_move_in_progress:
            # ドラッグ中の状態を維持
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # 複数ノード移動の終了を検知
        if event.button() == Qt.LeftButton and self._is_multi_move_in_progress:
            self._handle_multi_move_end()
        super().mouseReleaseEvent(event)

    def _handle_multi_move_end(self):
        """複数ノード移動の終了処理"""
        if not self._multi_move_start_positions:
            self._is_multi_move_in_progress = False
            return
        
        # 現在選択されているノードを取得
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        
        if len(selected_nodes) <= 1:
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 移動量を計算（実際に移動したノードの移動量を使用）
        moved_nodes = []
        delta_x = 0
        delta_y = 0
        
        for node in selected_nodes:
            if node in self._multi_move_start_positions:
                start_pos = self._multi_move_start_positions[node]
                current_pos = node.pos()
                node_delta_x = current_pos.x() - start_pos.x()
                node_delta_y = current_pos.y() - start_pos.y()
                
                # 移動したノードの移動量を記録
                if abs(node_delta_x) > 0.1 or abs(node_delta_y) > 0.1:  # 実際に移動したノード
                    moved_nodes.append(node)
                    delta_x = node_delta_x
                    delta_y = node_delta_y
                    break  # 最初に移動したノードの移動量を使用
        
        if not moved_nodes:
            # 移動していない場合は処理を終了
            self._is_multi_move_in_progress = False
            self._multi_move_start_positions.clear()
            return
        
        # 移動距離が十分大きい場合のみUndoスタックに追加
        move_distance = (delta_x ** 2 + delta_y ** 2) ** 0.5
        
        if move_distance > 5.0 and self.undo_stack is not None:
            # 各選択ノードの移動前後の位置を記録
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
            
            # 複数ノード移動コマンドを作成
            self.undo_stack.push(MoveMultipleNodesCommand(selected_nodes, old_positions, new_positions))
        
        # 状態をクリア
        self._is_multi_move_in_progress = False
        self._multi_move_start_positions.clear()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_nodes()
        elif event.key() == Qt.Key_Tab:
            self._add_node_with_tab()
        elif event.key() == Qt.Key_Escape:
            # Escapeキーで接続モードをキャンセル
            if self.pending_source_node is not None:
                self.pending_source_node.setSelected(False)
                self.pending_source_node = None
        elif event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
            # カーソルキーでノード選択を移動
            self._navigate_to_nearest_node(event.key())
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            # Commandキー + Aキーで全てのノードを選択
            self._select_all_nodes()
        else:
            super().keyPressEvent(event)

    def _select_all_nodes(self):
        """全てのノードを選択"""
        # 全てのNodeItemを取得
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        if not all_nodes:
            return  # ノードがない場合は何もしない
        
        # 全てのノードを選択状態にする
        for node in all_nodes:
            node.setSelected(True)
        
        # ステータスバーにメッセージを表示
        if hasattr(self.parent(), 'statusBar'):
            self.parent().statusBar().showMessage(f"{len(all_nodes)}個のノードを選択しました", 2000)

    def _delete_selected_nodes(self):
        """選択されたノードを削除"""
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            return
        
        # 複数ノードの削除を一つのコマンドとして扱う
        for node in selected_nodes:
            if self.undo_stack is not None:
                self.undo_stack.push(DeleteNodeCommand(self, node))

    def _add_node_with_tab(self):
        """Tabキーでノード追加（選択中ノードがあれば自動接続）"""
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        parent_node = selected_nodes[0] if selected_nodes else None
        
        # 新規ノードの配置位置を計算
        new_pos = None
        if parent_node is not None:
            new_pos = self._calculate_smart_position(parent_node)
        
        if self.undo_stack is not None:
            self.undo_stack.push(AddNodeCommand(self, "新規ノード", parent_node, new_pos))
        else:
            new_node = self.add_node("新規ノード", new_pos)
            if parent_node is not None:
                self._create_edge(parent_node, new_node)

    def _create_edge(self, source: 'NodeItem', target: 'NodeItem'):
        # クランク状の接続線を作成
        connection = CrankConnection(self.scene, source, target)
        # ノードにエッジを登録（双方）
        source.attach_edge(connection, target)
        target.attach_edge(connection, source)
        
        # 接続線作成後の交差解決は手動実行のみに変更（クラッシュを防ぐ）
        # self._resolve_connection_line_intersections()  # コメントアウト

        return connection

    def remove_edge(self, connection: 'CrankConnection', source: 'NodeItem', target: 'NodeItem') -> None:
        # ノードの参照から接続を除去
        source._edges = [(c, n) for (c, n) in source._edges if c is not connection]
        target._edges = [(c, n) for (c, n) in target._edges if c is not connection]
        connection.remove()

    def _calculate_smart_position(self, parent_node: 'NodeItem') -> QPointF:
        """親ノードから適切な位置に子ノードを配置（階層構造を考慮した配置）"""
        parent_pos = parent_node.pos()
        base_x = parent_pos.x() + 170  # 右側の基本位置（150+20）
        
        # 全ノードを取得
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        # 親ノードに接続されている子ノードを取得
        child_nodes = []
        for line_item, other_node in parent_node._edges:
            if other_node.pos().x() > parent_pos.x():  # 右側にあるノード
                child_nodes.append(other_node)
        
        if not child_nodes:
            # 子ノードがない場合は親ノードの真横（同じ高さ）に配置
            preferred_pos = QPointF(base_x, parent_pos.y())
            return self._find_collision_free_position(preferred_pos, all_nodes)
        
        # 既存の子ノードをY座標でソート
        child_nodes.sort(key=lambda n: n.pos().y())
        
        # 適切な挿入位置を計算（子ノード群の一番下に配置）
        insertion_pos = self._find_insertion_position(child_nodes, parent_pos.y(), base_x)
        
        # 挿入位置で衝突検出
        collision_free_pos = self._find_collision_free_position(insertion_pos, all_nodes)
        
        # 他のノードを最小限の距離下方向に移動（親ノードは固定）
        self._move_obstructing_nodes_down(collision_free_pos, all_nodes, parent_node)
        
        # 最終的な位置を決定（移動処理後の位置）
        return collision_free_pos


    def _calculate_parent_node_position(self) -> QPointF:
        """新しい親ノードの配置位置を計算（既存の親ノードの子ノード群の下に配置）"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        if not all_nodes:
            # ノードがない場合は中央に配置
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
        
        # 中心ノードの右側にある親ノードを取得
        parent_nodes = []
        for node in all_nodes:
            if node != center_node and node.pos().x() > center_node.pos().x():
                # 右側に子ノードがあるノードを親ノードとして判定
                has_right_children = False
                for connection, child in node._edges:
                    if child.pos().x() > node.pos().x():  # 右側の子ノード
                        has_right_children = True
                        break
                
                if has_right_children:
                    parent_nodes.append(node)
        
        if not parent_nodes:
            # 親ノードがない場合は中心ノードの右側に配置
            center_x = center_node.pos().x()
            center_y = center_node.pos().y()
            return QPointF(center_x + 200, center_y)
        
        # 各親ノードの子ノード群の最大Y座標を計算
        max_bottom_y = 0
        
        for parent in parent_nodes:
            children = []
            for connection, child in parent._edges:
                if child.pos().x() > parent.pos().x():  # 右側の子ノード
                    children.append(child)
            
            if children:
                # 子ノード群の最大Y座標を取得
                child_y_positions = [child.pos().y() for child in children]
                max_child_y = max(child_y_positions)
                max_bottom_y = max(max_bottom_y, max_child_y)
            else:
                # 子ノードがない場合は親ノードの位置
                max_bottom_y = max(max_bottom_y, parent.pos().y())
        
        # 既存の親ノードの子ノード群の下に配置
        node_height = 80
        min_spacing = 20
        new_y = max_bottom_y + node_height + min_spacing
        
        # 左側の基本位置（中心ノードの右側）
        center_x = center_node.pos().x()
        new_x = center_x + 200  # 中心ノードの右に200px
        
        return QPointF(new_x, new_y)

    def _find_insertion_position(self, child_nodes: list['NodeItem'], parent_y: float, base_x: float) -> QPointF:
        """子ノードの下位置に連ねるように挿入位置を見つける"""
        if not child_nodes:
            return QPointF(base_x, parent_y)
        
        node_height = 80  # ノードの高さ（マージン込み）
        spacing = 20      # ノード間の最小間隔
        
        # 既存の子ノードをY座標でソート
        child_nodes.sort(key=lambda n: n.pos().y())
        
        # 最も下にある子ノードの下に配置
        bottom_child = child_nodes[-1]
        insertion_y = bottom_child.pos().y() + node_height + spacing
        
        return QPointF(base_x, insertion_y)

    def _move_obstructing_nodes_down(self, new_child_pos: QPointF, all_nodes: list['NodeItem'], parent_node: 'NodeItem'):
        """新しい子ノードの位置で他のノードが邪魔になる場合、階層構造を考慮して下に移動"""
        node_width = 128
        node_height = 80
        min_spacing = 20
        
        # 新しい子ノードの境界矩形
        new_child_rect = QRectF(
            new_child_pos.x() - node_width / 2,
            new_child_pos.y() - node_height / 2,
            node_width,
            node_height
        )
        
        # 邪魔になるノードを特定
        obstructing_nodes = []
        for node in all_nodes:
            if node == parent_node:  # 親ノードは除外
                continue
            
            node_rect = QRectF(
                node.pos().x() - node_width / 2,
                node.pos().y() - node_height / 2,
                node_width,
                node_height
            )
            
            # 新しい子ノードと重なるか、最小間隔を下回る場合
            if new_child_rect.intersects(node_rect) or self._rects_too_close(new_child_rect, node_rect, min_spacing):
                obstructing_nodes.append(node)
        
        if not obstructing_nodes:
            return
        
        # 邪魔になるノードをY座標でソート（上から下へ）
        obstructing_nodes.sort(key=lambda n: n.pos().y())
        
        # 新しい子ノードの下に移動する必要があるノードを特定
        nodes_to_move_down = []
        for node in obstructing_nodes:
            if node.pos().y() >= new_child_pos.y():
                nodes_to_move_down.append(node)
        
        # 親ノードの位置を新しい子ノードと同じ高さに調整
        self._adjust_parent_to_child_height(parent_node, new_child_pos.y())
        
        # 階層構造を考慮してノードを下に移動
        self._move_hierarchical_nodes_down(nodes_to_move_down, new_child_pos, node_height, min_spacing)

    def _adjust_parent_to_child_height(self, parent_node: 'NodeItem', child_y: float):
        """親ノードの位置を子ノードと同じ高さに調整"""
        current_pos = parent_node.pos()
        new_pos = QPointF(current_pos.x(), child_y)
        parent_node.setPos(new_pos)
        parent_node._update_attached_lines()





    def _move_hierarchies_balanced(self, hierarchies: dict, new_child_pos: QPointF, 
                                 node_width: float, node_height: float, min_spacing: float):
        """階層構造をバランス良く下方向に移動"""
        # 階層レベルでソート（上から下へ）
        sorted_levels = sorted(hierarchies.keys())
        
        current_bottom_y = new_child_pos.y() + node_height / 2
        
        for level in sorted_levels:
            level_hierarchies = hierarchies[level]
            
            # 各ルートノードの階層を処理
            for root_node, nodes in level_hierarchies.items():
                # ノードをY座標でソート
                nodes.sort(key=lambda n: n.pos().y())
                
                # 階層全体の移動量を計算
                hierarchy_bottom = max(node.pos().y() + node_height / 2 for node in nodes)
                required_space = hierarchy_bottom - current_bottom_y + min_spacing
                
                if required_space > 0:
                    # 階層全体を下に移動
                    for node in nodes:
                        current_pos = node.pos()
                        new_y = current_pos.y() + required_space
                        new_pos = QPointF(current_pos.x(), new_y)
                        
                        node.setPos(new_pos)
                        node._update_attached_lines()
                    
                    # 最下部の位置を更新
                    current_bottom_y = hierarchy_bottom + required_space

    def _rects_too_close(self, rect1: QRectF, rect2: QRectF, min_spacing: float) -> bool:
        """2つの矩形が最小間隔を下回っているかチェック"""
        # 矩形間の最小距離を計算
        dx = max(0, max(rect1.left() - rect2.right(), rect2.left() - rect1.right()))
        dy = max(0, max(rect1.top() - rect2.bottom(), rect2.top() - rect1.bottom()))
        distance = (dx * dx + dy * dy) ** 0.5
        
        return distance < min_spacing

    def _adjust_parent_position(self, parent_node: 'NodeItem', new_child_pos: QPointF, existing_children: list['NodeItem']):
        """子ノードの配置に応じて親ノードの位置を調整（階層全体を考慮）"""
        if not existing_children:
            return  # 子ノードがない場合は調整不要
        
        # 既存の子ノードのY座標を取得
        child_y_positions = [child.pos().y() for child in existing_children]
        child_y_positions.append(new_child_pos.y())
        
        # 子ノードの中心Y座標を計算
        min_y = min(child_y_positions)
        max_y = max(child_y_positions)
        center_y = (min_y + max_y) / 2
        
        # 親ノードの現在位置
        current_parent_pos = parent_node.pos()
        
        # 親ノードを子ノードの中心に移動
        new_parent_y = center_y
        new_parent_pos = QPointF(current_parent_pos.x(), new_parent_y)
        
        # 他のノードとの衝突をチェック
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != parent_node]
        if self._is_position_free(new_parent_pos, all_nodes, 128, 80, 20):
            # 衝突しない場合は移動
            parent_node.setPos(new_parent_pos)
            # 接続線を更新
            parent_node._update_attached_lines()
            
            # 階層全体の調整を実行
            self._adjust_hierarchy_layout(parent_node)

    def _adjust_hierarchy_layout(self, modified_node: 'NodeItem'):
        """階層全体のレイアウトを調整して接続線の交差を最小化"""
        # 階層構造を分析
        hierarchy = self._analyze_hierarchy()
        
        # 各階層のノードを適切に配置
        for level, nodes in hierarchy.items():
            if len(nodes) > 1:
                self._arrange_nodes_in_level(nodes, level)

    def _adjust_entire_hierarchy_after_addition(self, parent_node: 'NodeItem', new_child_pos: QPointF):
        """新規ノード追加後の階層全体調整（全階層で接続線交差回避）"""
        # 完全な階層レイアウトを実行
        self._perform_complete_hierarchy_layout()

    def _arrange_nodes_in_level_with_propagation(self, nodes: list['NodeItem'], level: int):
        """同一階層のノードを適切に配置（上位階層への影響も考慮）"""
        if len(nodes) <= 1:
            return
        
        # ノードをX座標でソート
        nodes.sort(key=lambda n: n.pos().x())
        
        # 各ノードの子ノードのY座標範囲を計算
        node_ranges = []
        for node in nodes:
            child_y_positions = []
            for line_item, child_node in node._edges:
                if child_node.pos().x() > node.pos().x():  # 右側の子ノード
                    child_y_positions.append(child_node.pos().y())
            
            if child_y_positions:
                min_y = min(child_y_positions)
                max_y = max(child_y_positions)
                node_ranges.append((node, min_y, max_y))
            else:
                # 子ノードがない場合は現在のY座標を範囲とする
                y = node.pos().y()
                node_ranges.append((node, y, y))
        
        # ノード間の重なりを解消（上位階層への影響も考慮）
        self._resolve_overlaps_with_propagation(node_ranges, level)

    def _resolve_overlaps_with_propagation(self, node_ranges: list[tuple['NodeItem', float, float]], level: int):
        """ノード範囲の重なりを解消（上位階層への影響も考慮）"""
        if len(node_ranges) <= 1:
            return
        
        min_spacing = 100  # 最小間隔
        
        for i in range(1, len(node_ranges)):
            current_node, current_min, current_max = node_ranges[i]
            prev_node, prev_min, prev_max = node_ranges[i-1]
            
            # 前のノードとの重なりをチェック
            if current_min < prev_max + min_spacing:
                # 重なっている場合は下に移動
                offset = (prev_max + min_spacing) - current_min
                new_y = current_node.pos().y() + offset
                new_pos = QPointF(current_node.pos().x(), new_y)
                
                # 衝突チェック
                all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != current_node]
                if self._is_position_free(new_pos, all_nodes, 128, 80, 20):
                    current_node.setPos(new_pos)
                    current_node._update_attached_lines()
                    
                    # 範囲を更新
                    node_ranges[i] = (current_node, current_min + offset, current_max + offset)
                    
                    # 上位階層の親ノードも調整
                    self._adjust_parent_nodes_for_child_movement(current_node, offset)

    def _adjust_parent_nodes_for_child_movement(self, moved_node: 'NodeItem', offset: float):
        """子ノードの移動に応じて親ノードを調整"""
        # このノードの親ノードを探す
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        for potential_parent in all_nodes:
            if potential_parent != moved_node:
                for line_item, connected_node in potential_parent._edges:
                    if connected_node == moved_node and potential_parent.pos().x() < moved_node.pos().x():
                        # 親ノードが見つかった
                        self._adjust_single_parent_position(potential_parent)
                        break

    def _adjust_single_parent_position(self, parent_node: 'NodeItem'):
        """単一の親ノードの位置を子ノードの中心に調整"""
        child_y_positions = []
        for line_item, child_node in parent_node._edges:
            if child_node.pos().x() > parent_node.pos().x():  # 右側の子ノード
                child_y_positions.append(child_node.pos().y())
        
        if not child_y_positions:
            return
        
        # 子ノードの中心Y座標を計算
        min_y = min(child_y_positions)
        max_y = max(child_y_positions)
        center_y = (min_y + max_y) / 2
        
        # 親ノードを子ノードの中心に移動
        current_pos = parent_node.pos()
        new_pos = QPointF(current_pos.x(), center_y)
        
        # 衝突チェック
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != parent_node]
        if self._is_position_free(new_pos, all_nodes, 128, 80, 20):
            parent_node.setPos(new_pos)
            parent_node._update_attached_lines()

    def _should_move_related_nodes(self, moved_node: 'NodeItem', new_pos: QPointF) -> bool:
        """ノード移動時に他のノードと重なるかチェックし、関連ノードの移動が必要か判定"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != moved_node]
        
        # 移動先で他のノードと重なるかチェック
        if not self._is_position_free(new_pos, all_nodes, 128, 80, 20):
            return True
        
        # 同じ階層の他の親ノードとの関係をチェック
        moved_level = self._calculate_node_level(moved_node, all_nodes + [moved_node])
        same_level_nodes = []
        
        for node in all_nodes:
            node_level = self._calculate_node_level(node, all_nodes + [moved_node])
            if node_level == moved_level:
                same_level_nodes.append(node)
        
        # 同じ階層のノードが右側にある場合、それらとの位置関係をチェック
        moved_x = new_pos.x()
        for node in same_level_nodes:
            if node.pos().x() > moved_x:  # 右側にあるノード
                # 移動後の位置で接続線が交差する可能性があるかチェック
                if self._would_cause_line_crossing(moved_node, new_pos, node):
                    return True
        
        return False

    def _would_cause_line_crossing(self, moved_node: 'NodeItem', new_pos: QPointF, other_node: 'NodeItem') -> bool:
        """移動が接続線の交差を引き起こすかチェック"""
        # 移動したノードの子ノードを取得
        moved_children = []
        for line_item, child_node in moved_node._edges:
            if child_node.pos().x() > moved_node.pos().x():  # 右側の子ノード
                moved_children.append(child_node)
        
        # 他のノードの子ノードを取得
        other_children = []
        for line_item, child_node in other_node._edges:
            if child_node.pos().x() > other_node.pos().x():  # 右側の子ノード
                other_children.append(child_node)
        
        # 移動後の接続線が他の接続線と交差するかチェック
        for moved_child in moved_children:
            for other_child in other_children:
                if self._lines_intersect(new_pos, moved_child.pos(), other_node.pos(), other_child.pos()):
                    return True
        
        return False

    def _lines_intersect(self, p1: QPointF, p2: QPointF, p3: QPointF, p4: QPointF) -> bool:
        """2つの線分が交差するかチェック"""
        def ccw(A, B, C):
            return (C.y() - A.y()) * (B.x() - A.x()) > (B.y() - A.y()) * (C.x() - A.x())
        
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def _check_connection_line_intersections(self) -> list[tuple['NodeItem', 'NodeItem', 'NodeItem', 'NodeItem']]:
        """全ての接続線の交差を検出"""
        intersections = []
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        # 全てのノードペアの接続線をチェック
        for i, node1 in enumerate(all_nodes):
            for j, node2 in enumerate(all_nodes[i+1:], i+1):
                # ノード1の子ノードを取得
                children1 = []
                for connection, child in node1._edges:
                    if child.pos().x() > node1.pos().x():  # 右側の子ノード
                        children1.append(child)
                
                # ノード2の子ノードを取得
                children2 = []
                for connection, child in node2._edges:
                    if child.pos().x() > node2.pos().x():  # 右側の子ノード
                        children2.append(child)
                
                # 接続線同士の交差をチェック
                for child1 in children1:
                    for child2 in children2:
                        if self._lines_intersect(node1.pos(), child1.pos(), node2.pos(), child2.pos()):
                            intersections.append((node1, child1, node2, child2))
        
        return intersections
    
    def _resolve_connection_line_intersections(self):
        """接続線の交差を解決するためにノード位置を調整"""
        try:
            intersections = self._check_connection_line_intersections()
            
            if not intersections:
                return  # 交差がない場合は何もしない
            
            # 安全チェック：交差が多すぎる場合は処理をスキップ
            if len(intersections) > 20:
                print(f"警告: 交差が多すぎます ({len(intersections)}個)。処理をスキップします。")
                return
            
            # 交差している接続線のノードを取得
            affected_nodes = set()
            for node1, child1, node2, child2 in intersections:
                affected_nodes.add(node1)
                affected_nodes.add(child1)
                affected_nodes.add(node2)
                affected_nodes.add(child2)
            
            # 安全チェック：影響を受けるノードが多すぎる場合は処理をスキップ
            if len(affected_nodes) > 50:
                print(f"警告: 影響を受けるノードが多すぎます ({len(affected_nodes)}個)。処理をスキップします。")
                return
            
            # 影響を受けるノードの階層を分析
            hierarchy = self._analyze_hierarchy()
            
            # 階層ごとに交差を解決
            for level, nodes in hierarchy.items():
                level_nodes = [node for node in nodes if node in affected_nodes]
                if level_nodes:
                    self._resolve_intersections_at_level(level_nodes, intersections)
                    
        except Exception as e:
            print(f"接続線交差解決中のエラー: {e}")
            # エラーが発生した場合は処理を中断
    
    def _resolve_intersections_at_level(self, level_nodes: list['NodeItem'], intersections: list[tuple['NodeItem', 'NodeItem', 'NodeItem', 'NodeItem']]):
        """特定の階層レベルでの交差を解決"""
        if len(level_nodes) < 2:
            return
        
        try:
            # ノードをY座標でソート
            level_nodes.sort(key=lambda n: n.pos().y())
            
            # 交差を解決するためにノード間の間隔を調整
            min_spacing = 120  # 最小間隔（接続線の交差を避けるため少し大きめ）
            
            # 安全チェック：調整回数を制限
            max_adjustments = 10
            adjustment_count = 0
            
            # 各ノードの子ノードの位置も考慮して間隔を調整
            for i in range(len(level_nodes) - 1):
                if adjustment_count >= max_adjustments:
                    print(f"警告: 調整回数が上限に達しました ({max_adjustments}回)。処理を中断します。")
                    break
                    
                current_node = level_nodes[i]
                next_node = level_nodes[i + 1]
                
                # 現在のノードの子ノードの最大Y座標を取得
                current_max_y = current_node.pos().y()
                for connection, child in current_node._edges:
                    if child.pos().x() > current_node.pos().x():  # 右側の子ノード
                        current_max_y = max(current_max_y, child.pos().y())
                
                # 次のノードの最小Y座標を取得
                next_min_y = next_node.pos().y()
                for connection, child in next_node._edges:
                    if child.pos().x() > next_node.pos().x():  # 右側の子ノード
                        next_min_y = min(next_min_y, child.pos().y())
                
                # 間隔が狭すぎる場合は調整
                if next_min_y - current_max_y < min_spacing:
                    # 次のノードとその子ノードを下に移動
                    offset = min_spacing - (next_min_y - current_max_y)
                    # 安全チェック：移動距離が大きすぎる場合は制限
                    if offset > 500:
                        print(f"警告: 移動距離が大きすぎます ({offset}px)。制限します。")
                        offset = 500
                    
                    self._move_node_and_children_down(next_node, offset)
                    adjustment_count += 1
                    
        except Exception as e:
            print(f"階層レベル交差解決中のエラー: {e}")
            # エラーが発生した場合は処理を中断
    
    def _move_node_and_children_down(self, node: 'NodeItem', offset: float):
        """ノードとその子ノードを下に移動"""
        try:
            # 安全チェック：移動距離が大きすぎる場合は制限
            if abs(offset) > 1000:
                print(f"警告: 移動距離が大きすぎます ({offset}px)。制限します。")
                offset = 1000 if offset > 0 else -1000
            
            # ノード自体を移動
            new_y = node.pos().y() + offset
            node.setPos(QPointF(node.pos().x(), new_y))
            
            # 子ノードも移動（再帰的な移動を防ぐため制限）
            child_count = 0
            max_children = 20  # 子ノード数の上限
            
            for connection, child in node._edges:
                if child_count >= max_children:
                    print(f"警告: 子ノード数が上限に達しました ({max_children}個)。処理を中断します。")
                    break
                    
                if child.pos().x() > node.pos().x():  # 右側の子ノード
                    child_new_y = child.pos().y() + offset
                    child.setPos(QPointF(child.pos().x(), child_new_y))
                    # 子ノードの接続線を更新
                    child._update_attached_lines()
                    child_count += 1
            
            # ノードの接続線を更新
            node._update_attached_lines()
            
        except Exception as e:
            print(f"ノード移動中のエラー: {e}")
            # エラーが発生した場合は処理を中断

    def move_node_with_undo(self, node: 'NodeItem', new_pos: QPointF):
        """Undo機能付きでノードを移動"""
        if self.undo_stack is not None:
            old_pos = node.pos()
            if old_pos != new_pos:
                # 移動先で他のノードと重なるかチェック
                if self._should_move_related_nodes(node, new_pos):
                    # 重なる場合は関連ノードも移動
                    self.undo_stack.push(MoveNodeWithRelatedCommand(self, node, old_pos, new_pos))
                else:
                    # 重ならない場合は単純な移動のみ
                    self.undo_stack.push(MoveNodeCommand(node, old_pos, new_pos))
        else:
            # Undoスタックがない場合は直接移動
            node.setPos(new_pos)
            node._update_attached_lines()


    def _update_all_connections(self):
        """全ノードの接続線を更新"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        for node in all_nodes:
            node._update_attached_lines()

    def _export_to_json(self) -> str:
        """マインドマップをJSON形式でエクスポート"""
        import json
        
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        
        # ノード情報を収集
        nodes_data = []
        for node in all_nodes:
            pos = node.pos()
            text = node.text_item.toPlainText()
            nodes_data.append({
                "id": id(node),  # ノードの一意識別子
                "text": text,
                "x": pos.x(),
                "y": pos.y()
            })
        
        # エッジ情報を収集
        edges_data = []
        for node in all_nodes:
            for line_item, other_node in node._edges:
                # 重複を避けるため、IDが小さい方から大きい方への接続のみ記録
                if id(node) < id(other_node):
                    edges_data.append({
                        "from": id(node),
                        "to": id(other_node)
                    })
        
        data = {
            "nodes": nodes_data,
            "edges": edges_data,
            "version": "1.0"
        }
        
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _import_from_json(self, json_data: str):
        """JSON形式からマインドマップをインポート"""
        import json
        
        # 既存のノードとエッジをクリア
        self.scene.clear()
        
        # Undoスタックもクリア
        if self.undo_stack:
            self.undo_stack.clear()
        
        data = json.loads(json_data)
        
        # ノードIDからノードオブジェクトへのマッピング
        node_map = {}
        
        # ノードを作成
        for node_data in data.get("nodes", []):
            node = self.add_node(
                node_data["text"], 
                QPointF(node_data["x"], node_data["y"])
            )
            node_map[node_data["id"]] = node
        
        # エッジを作成
        for edge_data in data.get("edges", []):
            from_id = edge_data["from"]
            to_id = edge_data["to"]
            
            if from_id in node_map and to_id in node_map:
                from_node = node_map[from_id]
                to_node = node_map[to_id]
                self._create_edge(from_node, to_node)

    def _perform_complete_hierarchy_layout(self):
        """完全な階層レイアウトを実行（接続線交差を完全回避）"""
        # 階層構造を分析
        hierarchy = self._analyze_hierarchy()
        
        if not hierarchy:
            return
        
        # 各階層のノードを適切に配置
        for level in sorted(hierarchy.keys()):
            nodes = hierarchy[level]
            if len(nodes) > 1:
                self._arrange_level_with_no_crossing(nodes, level)
        
        # 全ノードの接続線を更新
        self._update_all_connections()

    def _arrange_level_with_no_crossing(self, nodes: list['NodeItem'], level: int):
        """同一階層のノードを接続線交差なしで配置"""
        if len(nodes) <= 1:
            return
        
        # ノードをX座標でソート
        nodes.sort(key=lambda n: n.pos().x())
        
        # 各ノードの子ノード範囲を計算
        node_ranges = []
        for node in nodes:
            child_y_positions = []
            for line_item, child_node in node._edges:
                if child_node.pos().x() > node.pos().x():  # 右側の子ノード
                    child_y_positions.append(child_node.pos().y())
            
            if child_y_positions:
                min_y = min(child_y_positions)
                max_y = max(child_y_positions)
                node_ranges.append((node, min_y, max_y, len(child_y_positions)))
            else:
                # 子ノードがない場合は現在のY座標を範囲とする
                y = node.pos().y()
                node_ranges.append((node, y, y, 0))
        
        # 接続線交差を避ける配置を計算
        self._calculate_no_crossing_layout(node_ranges)

    def _calculate_no_crossing_layout(self, node_ranges: list[tuple['NodeItem', float, float, int]]):
        """接続線交差を避けるレイアウトを計算"""
        if len(node_ranges) <= 1:
            return
        
        # 各ノードの理想的なY座標を計算
        ideal_positions = []
        
        for i, (node, min_y, max_y, child_count) in enumerate(node_ranges):
            if child_count == 0:
                # 子ノードがない場合は現在位置を維持
                ideal_y = node.pos().y()
            else:
                # 子ノードがある場合は子ノード群の中心
                ideal_y = (min_y + max_y) / 2
            
            ideal_positions.append((node, ideal_y, min_y, max_y))
        
        # 重なりを解消
        self._resolve_position_conflicts(ideal_positions)

    def _resolve_position_conflicts(self, positions: list[tuple['NodeItem', float, float, float]]):
        """位置の重なりを解消"""
        if len(positions) <= 1:
            return
        
        min_spacing = 120  # ノード間の最小間隔
        
        # 位置を調整
        for i in range(1, len(positions)):
            current_node, ideal_y, min_y, max_y = positions[i]
            prev_node, prev_ideal_y, prev_min_y, prev_max_y = positions[i-1]
            
            # 前のノードとの重なりをチェック
            if ideal_y < prev_ideal_y + min_spacing:
                # 重なっている場合は下に移動
                new_y = prev_ideal_y + min_spacing
                
                # 新しい位置でノードを移動
                new_pos = QPointF(current_node.pos().x(), new_y)
                
                # 衝突チェック
                all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != current_node]
                if self._is_position_free(new_pos, all_nodes, 128, 80, 20):
                    current_node.setPos(new_pos)
                    current_node._update_attached_lines()
                    
                    # 位置情報を更新
                    positions[i] = (current_node, new_y, min_y + (new_y - ideal_y), max_y + (new_y - ideal_y))
                else:
                    # 衝突する場合はさらに下に移動
                    offset = 50
                    while offset < 500:  # 最大500pxまで試行
                        new_y = ideal_y + offset
                        new_pos = QPointF(current_node.pos().x(), new_y)
                        
                        if self._is_position_free(new_pos, all_nodes, 128, 80, 20):
                            current_node.setPos(new_pos)
                            current_node._update_attached_lines()
                            positions[i] = (current_node, new_y, min_y + offset, max_y + offset)
                            break
                        offset += 50

    def _analyze_hierarchy(self) -> dict[int, list['NodeItem']]:
        """階層構造を分析してレベルごとにノードを分類"""
        all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem)]
        hierarchy = {}
        
        # 各ノードの階層レベルを計算
        for node in all_nodes:
            level = self._calculate_node_level(node, all_nodes)
            if level not in hierarchy:
                hierarchy[level] = []
            hierarchy[level].append(node)
        
        return hierarchy

    def _calculate_node_level(self, node: 'NodeItem', all_nodes: list['NodeItem']) -> int:
        """ノードの階層レベルを計算（0が最上位）"""
        # 親ノードを探す
        for other_node in all_nodes:
            if other_node != node:
                for line_item, connected_node in other_node._edges:
                    if connected_node == node and other_node.pos().x() < node.pos().x():
                        # このノードの親が見つかった
                        return self._calculate_node_level(other_node, all_nodes) + 1
        
        # 親ノードが見つからない場合は最上位レベル
        return 0

    def _arrange_nodes_in_level(self, nodes: list['NodeItem'], level: int):
        """同一階層のノードを適切に配置"""
        if len(nodes) <= 1:
            return
        
        # ノードをX座標でソート
        nodes.sort(key=lambda n: n.pos().x())
        
        # 各ノードの子ノードのY座標範囲を計算
        node_ranges = []
        for node in nodes:
            child_y_positions = []
            for line_item, child_node in node._edges:
                if child_node.pos().x() > node.pos().x():  # 右側の子ノード
                    child_y_positions.append(child_node.pos().y())
            
            if child_y_positions:
                min_y = min(child_y_positions)
                max_y = max(child_y_positions)
                node_ranges.append((node, min_y, max_y))
            else:
                # 子ノードがない場合は現在のY座標を範囲とする
                y = node.pos().y()
                node_ranges.append((node, y, y))
        
        # ノード間の重なりを解消
        self._resolve_overlaps(node_ranges)

    def _resolve_overlaps(self, node_ranges: list[tuple['NodeItem', float, float]]):
        """ノード範囲の重なりを解消"""
        if len(node_ranges) <= 1:
            return
        
        min_spacing = 100  # 最小間隔
        
        for i in range(1, len(node_ranges)):
            current_node, current_min, current_max = node_ranges[i]
            prev_node, prev_min, prev_max = node_ranges[i-1]
            
            # 前のノードとの重なりをチェック
            if current_min < prev_max + min_spacing:
                # 重なっている場合は下に移動
                offset = (prev_max + min_spacing) - current_min
                new_y = current_node.pos().y() + offset
                new_pos = QPointF(current_node.pos().x(), new_y)
                
                # 衝突チェック
                all_nodes = [item for item in self.scene.items() if isinstance(item, NodeItem) and item != current_node]
                if self._is_position_free(new_pos, all_nodes, 128, 80, 20):
                    current_node.setPos(new_pos)
                    current_node._update_attached_lines()
                    
                    # 範囲を更新
                    node_ranges[i] = (current_node, current_min + offset, current_max + offset)

    def _find_collision_free_position(self, preferred_pos: QPointF, existing_nodes: list['NodeItem']) -> QPointF:
        """指定位置から全ノードとの衝突を避ける位置を探す（下方向優先）"""
        node_width = 128   # ノードの幅（マージン込み）
        node_height = 80   # ノードの高さ（マージン込み）
        min_spacing = 20   # 最小間隔
        
        # まず希望位置をチェック
        if self._is_position_free(preferred_pos, existing_nodes, node_width, node_height, min_spacing):
            return preferred_pos
        
        # 候補位置のリスト（下方向優先）
        candidates = [
            QPointF(preferred_pos.x(), preferred_pos.y() + 100),  # 下
            QPointF(preferred_pos.x() + 50, preferred_pos.y()),   # 右
            QPointF(preferred_pos.x() - 50, preferred_pos.y()),   # 左
            QPointF(preferred_pos.x(), preferred_pos.y() - 100),  # 上
        ]
        
        # 下方向の候補を追加（上方向は除外）
        for offset_y in range(50, 301, 50):
            candidates.append(QPointF(preferred_pos.x(), preferred_pos.y() + offset_y))
        
        # 右方向の候補を追加
        for offset_x in range(50, 201, 50):
            candidates.append(QPointF(preferred_pos.x() + offset_x, preferred_pos.y()))
            candidates.append(QPointF(preferred_pos.x() - offset_x, preferred_pos.y()))
        
        for candidate in candidates:
            if self._is_position_free(candidate, existing_nodes, node_width, node_height, min_spacing):
                return candidate
        
        # 全ての候補が衝突する場合は、最も近い空き位置を探す
        return self._find_nearest_free_position(preferred_pos, existing_nodes, node_width, node_height, min_spacing)

    def _is_position_free(self, pos: QPointF, existing_nodes: list['NodeItem'], 
                         node_width: float, node_height: float, min_spacing: float) -> bool:
        """指定位置が空いているかチェック（ノードと接続線の両方を考慮）"""
        # ノード同士の衝突判定
        for node in existing_nodes:
            node_pos = node.pos()
            # 矩形の衝突判定
            if (abs(pos.x() - node_pos.x()) < node_width + min_spacing and
                abs(pos.y() - node_pos.y()) < node_height + min_spacing):
                return False
        
        # 接続線との接触判定
        if self._would_intersect_connection_lines(pos, node_width, node_height, min_spacing):
            return False
        
        return True
    
    def _would_intersect_connection_lines(self, pos: QPointF, node_width: float, node_height: float, min_spacing: float) -> bool:
        """指定位置のノードが接続線と交差するかチェック"""
        # 新しいノードの境界矩形
        new_rect = QRectF(pos.x() - node_width/2 - min_spacing, 
                         pos.y() - node_height/2 - min_spacing,
                         node_width + min_spacing * 2, 
                         node_height + min_spacing * 2)
        
        # 全ての接続線をチェック
        for item in self.scene.items():
            if isinstance(item, QGraphicsLineItem):
                line_rect = item.boundingRect()
                # 線の境界矩形を少し拡張
                expanded_line_rect = line_rect.adjusted(-min_spacing, -min_spacing, min_spacing, min_spacing)
                
                if new_rect.intersects(expanded_line_rect):
                    return True
        
        return False
    
    def _is_position_free_for_node(self, pos: QPointF, moving_node: 'NodeItem') -> bool:
        """ノード移動時の位置が空いているかチェック（移動中のノードは除外）"""
        try:
            node_width = 128   # ノードの幅（マージン込み）
            node_height = 80   # ノードの高さ（マージン込み）
            min_spacing = 20   # 最小間隔
            
            # 移動中のノード以外の全てのノードを取得
            existing_nodes = [item for item in self.scene.items() 
                             if isinstance(item, NodeItem) and item != moving_node]
            
            # 安全チェック：ノード数が多すぎる場合は簡易チェックのみ
            if len(existing_nodes) > 100:
                # 簡易チェック：近くのノードのみチェック
                for node in existing_nodes:
                    node_pos = node.pos()
                    distance = ((pos.x() - node_pos.x()) ** 2 + (pos.y() - node_pos.y()) ** 2) ** 0.5
                    if distance < 200:  # 200px以内のノードのみ詳細チェック
                        if (abs(pos.x() - node_pos.x()) < node_width + min_spacing and
                            abs(pos.y() - node_pos.y()) < node_height + min_spacing):
                            return False
                return True
            
            # ノード同士の衝突判定
            for node in existing_nodes:
                node_pos = node.pos()
                # 矩形の衝突判定
                if (abs(pos.x() - node_pos.x()) < node_width + min_spacing and
                    abs(pos.y() - node_pos.y()) < node_height + min_spacing):
                    return False
            
            # 接続線との接触判定（移動中のノードの接続線は除外）
            if self._would_intersect_connection_lines_for_node(pos, node_width, node_height, min_spacing, moving_node):
                return False
            
            return True
            
        except Exception as e:
            print(f"位置チェック中のエラー: {e}")
            # エラーが発生した場合は安全のためFalseを返す
            return False
    
    def _would_intersect_connection_lines_for_node(self, pos: QPointF, node_width: float, node_height: float, 
                                                 min_spacing: float, moving_node: 'NodeItem') -> bool:
        """ノード移動時の接続線との交差チェック（移動中のノードの接続線は除外）"""
        # 新しいノードの境界矩形
        new_rect = QRectF(pos.x() - node_width/2 - min_spacing, 
                         pos.y() - node_height/2 - min_spacing,
                         node_width + min_spacing * 2, 
                         node_height + min_spacing * 2)
        
        # 移動中のノードに関連する接続線を取得
        moving_node_connections = set()
        for connection, other_node in moving_node._edges:
            moving_node_connections.add(connection)
        
        # 全ての接続線をチェック（移動中のノードの接続線は除外）
        for item in self.scene.items():
            if isinstance(item, QGraphicsLineItem):
                # 移動中のノードの接続線かチェック
                is_moving_node_connection = False
                for connection in moving_node_connections:
                    if (hasattr(connection, 'horizontal_line1') and 
                        (item == connection.horizontal_line1 or 
                         item == connection.vertical_line or 
                         item == connection.horizontal_line2)):
                        is_moving_node_connection = True
                        break
                
                if is_moving_node_connection:
                    continue  # 移動中のノードの接続線はスキップ
                
                line_rect = item.boundingRect()
                # 線の境界矩形を少し拡張
                expanded_line_rect = line_rect.adjusted(-min_spacing, -min_spacing, min_spacing, min_spacing)
                
                if new_rect.intersects(expanded_line_rect):
                    return True
        
        return False

    def _find_nearest_free_position(self, preferred_pos: QPointF, existing_nodes: list['NodeItem'],
                                   node_width: float, node_height: float, min_spacing: float) -> QPointF:
        """最も近い空き位置を探す（下方向優先のスパイラル検索）"""
        step = 50
        max_radius = 500
        
        for radius in range(step, max_radius + 1, step):
            # 下方向を優先して円周上の位置をチェック（180度から360度、0度から180度の順）
            angles = list(range(180, 360, 30)) + list(range(0, 180, 30))
            for angle in angles:
                import math
                x = preferred_pos.x() + radius * math.cos(math.radians(angle))
                y = preferred_pos.y() + radius * math.sin(math.radians(angle))
                candidate = QPointF(x, y)
                
                if self._is_position_free(candidate, existing_nodes, node_width, node_height, min_spacing):
                    return candidate
        
        # 最後の手段：希望位置から遠く離れた下方向の場所
        return QPointF(preferred_pos.x() + 300, preferred_pos.y() + 300)


class TransparencyDialog(QDialog):
    """透明度設定ダイアログ"""
    def __init__(self, parent=None, background_transparency=1.0, node_transparency=1.0, line_transparency=1.0):
        super().__init__(parent)
        self.setWindowTitle("透明度設定")
        self.setModal(True)
        self.resize(400, 250)
        
        layout = QVBoxLayout(self)
        
        # 説明ラベル
        label = QLabel("各要素の透明度を個別に設定してください:")
        layout.addWidget(label)
        
        # 背景透明度設定
        bg_layout = QHBoxLayout()
        bg_label = QLabel("背景透明度:")
        bg_layout.addWidget(bg_label)
        
        self.bg_slider = QSlider(Qt.Horizontal)
        self.bg_slider.setMinimum(0)  # 0% (完全透明)
        self.bg_slider.setMaximum(100)  # 100% (不透明)
        self.bg_slider.setValue(int(background_transparency * 100))
        self.bg_slider.valueChanged.connect(self._on_bg_slider_changed)
        bg_layout.addWidget(self.bg_slider)
        
        self.bg_percent_label = QLabel(f"{int(background_transparency * 100):.0f}%")
        self.bg_percent_label.setMinimumWidth(50)
        bg_layout.addWidget(self.bg_percent_label)
        
        layout.addLayout(bg_layout)
        
        # ノード透明度設定
        node_layout = QHBoxLayout()
        node_label = QLabel("ノード透明度:")
        node_layout.addWidget(node_label)
        
        self.node_slider = QSlider(Qt.Horizontal)
        self.node_slider.setMinimum(10)  # 10% (最小)
        self.node_slider.setMaximum(100)  # 100% (不透明)
        self.node_slider.setValue(int(node_transparency * 100))
        self.node_slider.valueChanged.connect(self._on_node_slider_changed)
        node_layout.addWidget(self.node_slider)
        
        self.node_percent_label = QLabel(f"{int(node_transparency * 100):.0f}%")
        self.node_percent_label.setMinimumWidth(50)
        node_layout.addWidget(self.node_percent_label)
        
        layout.addLayout(node_layout)
        
        # 接続線透明度設定
        line_layout = QHBoxLayout()
        line_label = QLabel("接続線透明度:")
        line_layout.addWidget(line_label)
        
        self.line_slider = QSlider(Qt.Horizontal)
        self.line_slider.setMinimum(10)  # 10% (最小)
        self.line_slider.setMaximum(100)  # 100% (不透明)
        self.line_slider.setValue(int(line_transparency * 100))
        self.line_slider.valueChanged.connect(self._on_line_slider_changed)
        line_layout.addWidget(self.line_slider)
        
        self.line_percent_label = QLabel(f"{int(line_transparency * 100):.0f}%")
        self.line_percent_label.setMinimumWidth(50)
        line_layout.addWidget(self.line_percent_label)
        
        layout.addLayout(line_layout)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def _on_bg_slider_changed(self, value):
        """背景透明度スライダーの値が変更された時の処理"""
        self.bg_percent_label.setText(f"{value:.0f}%")
    
    def _on_node_slider_changed(self, value):
        """ノード透明度スライダーの値が変更された時の処理"""
        self.node_percent_label.setText(f"{value:.0f}%")
    
    def _on_line_slider_changed(self, value):
        """接続線透明度スライダーの値が変更された時の処理"""
        self.line_percent_label.setText(f"{value:.0f}%")
    
    def get_background_transparency(self):
        """背景透明度の値を取得（0.0-1.0）"""
        return self.bg_slider.value() / 100.0
    
    def get_node_transparency(self):
        """ノード透明度の値を取得（0.1-1.0）"""
        return self.node_slider.value() / 100.0
    
    def get_line_transparency(self):
        """接続線透明度の値を取得（0.1-1.0）"""
        return self.line_slider.value() / 100.0


class ZoomSpeedDialog(QDialog):
    """ズームスピード設定ダイアログ"""
    def __init__(self, parent=None, current_speed=1.15):
        super().__init__(parent)
        self.setWindowTitle("ズームスピード設定")
        self.setModal(True)
        self.resize(300, 120)
        
        # レイアウト
        layout = QVBoxLayout()
        
        # ラベル
        label = QLabel("ズームスピードを調整してください:")
        layout.addWidget(label)
        
        # スライダーとラベルのコンテナ
        slider_layout = QHBoxLayout()
        
        # スライダー（より細かい調整が可能な範囲）
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(200)  # 0.5%刻みで1-100%の範囲
        self.slider.setValue(int((current_speed - 1.0) * 200))  # 0.5%刻み
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.slider)
        
        # パーセント表示ラベル
        initial_percent = (current_speed - 1.0) * 100
        self.percent_label = QLabel(f"{initial_percent:.1f}%")
        self.percent_label.setMinimumWidth(50)
        slider_layout.addWidget(self.percent_label)
        
        layout.addLayout(slider_layout)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # 初期値保存
        self.initial_speed = current_speed
    
    def _on_slider_changed(self, value):
        """スライダー値変更時の処理"""
        # 0.5%刻みで表示
        percent = value / 2.0
        self.percent_label.setText(f"{percent:.1f}%")
    
    def get_zoom_speed(self):
        """設定されたズームスピードを取得"""
        # 0.5%刻みで計算
        percent = self.slider.value() / 2.0
        return 1.0 + (percent / 100.0)


class AddNodeCommand(QUndoCommand):
    def __init__(self, view: MindMapView, label: str = "新規ノード", parent_node: NodeItem | None = None, pos: QPointF | None = None, is_parent_node: bool = False):
        super().__init__("ノード追加")
        self.view = view
        self.label = label
        self.parent_node = parent_node
        self.pos = pos
        self.is_parent_node = is_parent_node
        self.node: NodeItem | None = None
        self.connection: CrankConnection | None = None

    def redo(self):
        if self.node is None:
            self.node = self.view.add_node(self.label, self.pos, self.is_parent_node)
        else:
            self.view.scene.addItem(self.node)
        if self.parent_node is not None and self.connection is None:
            self.connection = self.view._create_edge(self.parent_node, self.node)

    def undo(self):
        # エッジがあれば先に削除
        if self.connection is not None and self.parent_node is not None and self.node is not None:
            self.view.remove_edge(self.connection, self.parent_node, self.node)
            self.connection = None
        if self.node is not None:
            self.view.scene.removeItem(self.node)


class ConnectNodesCommand(QUndoCommand):
    def __init__(self, view: MindMapView, source: NodeItem, target: NodeItem):
        super().__init__("ノード接続")
        self.view = view
        self.source = source
        self.target = target
        self.connection: CrankConnection | None = None

    def redo(self):
        if self.connection is None:
            self.connection = self.view._create_edge(self.source, self.target)
        else:
            # 削除後のやり直し
            self.source.attach_edge(self.connection, self.target)
            self.target.attach_edge(self.connection, self.source)

    def undo(self):
        if self.connection is not None:
            self.view.remove_edge(self.connection, self.source, self.target)


class MoveNodeCommand(QUndoCommand):
    def __init__(self, node: NodeItem, old_pos: QPointF, new_pos: QPointF):
        super().__init__("ノード移動")
        self.node = node
        self.old_pos = QPointF(old_pos)
        self.new_pos = QPointF(new_pos)

    def redo(self):
        self.node.setPos(self.new_pos)
        self.node._update_attached_lines()

    def undo(self):
        self.node.setPos(self.old_pos)
        self.node._update_attached_lines()


class MoveMultipleNodesCommand(QUndoCommand):
    def __init__(self, nodes: list[NodeItem], old_positions: list[QPointF], new_positions: list[QPointF]):
        super().__init__("複数ノード移動")
        self.nodes = nodes
        self.old_positions = [QPointF(pos) for pos in old_positions]
        self.new_positions = [QPointF(pos) for pos in new_positions]

    def redo(self):
        for node, new_pos in zip(self.nodes, self.new_positions):
            node.setPos(new_pos)
        # 全てのノードの接続線を更新
        for node in self.nodes:
            node._update_attached_lines()

    def undo(self):
        for node, old_pos in zip(self.nodes, self.old_positions):
            node.setPos(old_pos)
        # 全てのノードの接続線を更新
        for node in self.nodes:
            node._update_attached_lines()


class MoveNodeWithRelatedCommand(QUndoCommand):
    def __init__(self, view: MindMapView, node: NodeItem, old_pos: QPointF, new_pos: QPointF):
        super().__init__("ノード移動（関連調整）")
        self.view = view
        self.node = node
        self.old_pos = QPointF(old_pos)
        self.new_pos = QPointF(new_pos)
        self.related_moves: list[tuple[NodeItem, QPointF, QPointF]] = []

    def redo(self):
        # 初回実行時のみ関連ノードの移動を計算
        if not self.related_moves:
            # 移動量を計算
            delta_y = self.new_pos.y() - self.old_pos.y()
            
            # 関連する親ノードを特定
            related_nodes = self._find_related_parent_nodes(self.node)
            
            # 関連ノードの移動を記録
            for related_node in related_nodes:
                old_related_pos = related_node.pos()
                new_related_pos = QPointF(old_related_pos.x(), old_related_pos.y() + delta_y)
                self.related_moves.append((related_node, old_related_pos, new_related_pos))
        
        # メインノードを移動
        self.node.setPos(self.new_pos)
        self.node._update_attached_lines()
        
        # 関連ノードを移動
        for related_node, old_pos, new_pos in self.related_moves:
            related_node.setPos(new_pos)
            related_node._update_attached_lines()

    def undo(self):
        # メインノードを元の位置に戻す
        self.node.setPos(self.old_pos)
        self.node._update_attached_lines()
        
        # 関連ノードを元の位置に戻す
        for related_node, old_pos, new_pos in self.related_moves:
            related_node.setPos(old_pos)
            related_node._update_attached_lines()

    def _find_related_parent_nodes(self, moved_node: NodeItem) -> list[NodeItem]:
        """移動したノードと関連する親ノードを特定"""
        all_nodes = [item for item in self.view.scene.items() if isinstance(item, NodeItem)]
        
        # 移動したノードの階層レベルを取得
        moved_level = self.view._calculate_node_level(moved_node, all_nodes)
        
        # 同じ階層の他の親ノードを取得
        same_level_nodes = []
        for node in all_nodes:
            if node != moved_node:
                node_level = self.view._calculate_node_level(node, all_nodes)
                if node_level == moved_level:
                    same_level_nodes.append(node)
        
        # 移動したノードより右側にある同じ階層のノードを関連ノードとする
        related_nodes = []
        moved_x = moved_node.pos().x()
        for node in same_level_nodes:
            if node.pos().x() > moved_x:  # 右側にあるノード
                related_nodes.append(node)
        
        return related_nodes


class RenameNodeCommand(QUndoCommand):
    def __init__(self, node: NodeItem, old_text: str, new_text: str):
        super().__init__("ノード名変更")
        self.node = node
        self.old_text = old_text
        self.new_text = new_text

    def redo(self):
        self.node._rename_node(self.new_text)

    def undo(self):
        self.node._rename_node(self.old_text)


class DeleteNodeCommand(QUndoCommand):
    def __init__(self, view: MindMapView, node: NodeItem):
        super().__init__("ノード削除")
        self.view = view
        self.node = node
        self.connected_edges: list[tuple[CrankConnection, NodeItem, NodeItem]] = []
        self.node_pos = node.pos()

    def redo(self):
        # 接続されているエッジを記録して削除
        for connection, other_node in self.node._edges:
            self.connected_edges.append((connection, self.node, other_node))
            self.view.remove_edge(connection, self.node, other_node)
        
        # ノードを削除
        self.view.scene.removeItem(self.node)

    def undo(self):
        # ノードを復元
        self.view.scene.addItem(self.node)
        self.node.setPos(self.node_pos)
        
        # エッジを復元
        for connection, source, target in self.connected_edges:
            source.attach_edge(connection, target)
            target.attach_edge(connection, source)
        self.connected_edges.clear()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mind Map (PySide6)")
        self.resize(1100, 750)
        
        # 透明度の初期設定
        self.transparency = 1.0  # デフォルトは不透明

        self.view = MindMapView(self)
        self.setCentralWidget(self.view)
        
        # macOS用の背景透明化設定
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        
        # ウィンドウのスタイルシートも設定
        self.setStyleSheet("""
            QMainWindow { 
                background: transparent; 
            }
            QToolBar {
                background: rgba(240, 240, 240, 200);
            }
        """)
        
        # ビューにフォーカスを設定（キーイベントを受け取るため）
        self.view.setFocusPolicy(Qt.StrongFocus)
        self.view.setFocus()

        # Undoスタック
        self.undo_stack = QUndoStack(self)
        self.view.undo_stack = self.undo_stack

        # 中心ノード（起動時に選択状態）
        center_node = self.view.add_node("中心テーマ", QPointF(0, 0))
        center_node.setSelected(True)
        
        # 背景を透明に設定
        self.view.set_background_transparency(0.0)
        

        # ツールバー
        toolbar = QToolBar("Tools", self)
        self.addToolBar(toolbar)

        # Undo/Redo アクション
        undo_action = self.undo_stack.createUndoAction(self, "取り消し")
        undo_action.setShortcut(QKeySequence.Undo)
        redo_action = self.undo_stack.createRedoAction(self, "やり直し")
        redo_action.setShortcut(QKeySequence.Redo)
        toolbar.addAction(undo_action)
        toolbar.addAction(redo_action)

        action_add = QAction("ノード追加", self)
        action_add.setStatusTip("新しいノードを中央に追加 (Tabキー)")
        action_add.setShortcut(QKeySequence(Qt.Key_Tab))
        def on_add_node():
            parent_node = None
            new_pos = None
            is_parent_node = False
            
            # 選択されたノードがあれば親ノードとして使用（接続モードに関係なく）
            selected = [it for it in self.view.scene.selectedItems() if isinstance(it, NodeItem)]
            if selected:
                parent_node = selected[0]
                # スマート配置で親ノードの右側に配置
                new_pos = self.view._calculate_smart_position(parent_node)
                is_parent_node = False  # 子ノード
            else:
                # 選択されたノードがない場合は親ノードとして追加
                is_parent_node = True
                new_pos = None  # 位置は自動計算
            
            if self.undo_stack is not None:
                self.undo_stack.push(AddNodeCommand(self.view, "新規ノード", parent_node, new_pos, is_parent_node))
            else:
                new_node = self.view.add_node("新規ノード", new_pos, is_parent_node)
                if parent_node is not None:
                    self.view._create_edge(parent_node, new_node)
        action_add.triggered.connect(on_add_node)
        toolbar.addAction(action_add)

        # 全選択ボタン
        action_select_all = QAction("全選択", self)
        action_select_all.setStatusTip("全てのノードを選択 (Cmd+A)")
        action_select_all.setShortcut(QKeySequence.SelectAll)
        action_select_all.triggered.connect(self.view._select_all_nodes)
        toolbar.addAction(action_select_all)

        action_connect = QAction("接続モード", self)
        action_connect.setCheckable(True)
        action_connect.setChecked(False)  # デフォルトでOFF（Shiftキーで操作）
        action_connect.setStatusTip("Shiftキーを押しながらノードをクリックして接続")
        action_connect.toggled.connect(self._toggle_connect_mode)
        toolbar.addAction(action_connect)

        # フィットボタン
        action_fit = QAction("フィット", self)
        action_fit.setStatusTip("全ノードが画面に収まるよう調整")
        action_fit.triggered.connect(self.view.fit_all_nodes)
        toolbar.addAction(action_fit)

        # ズームスピード調整ボタン
        action_zoom_speed = QAction("ズーム速度", self)
        action_zoom_speed.setStatusTip("ズームスピードをパーセントで設定")
        action_zoom_speed.triggered.connect(self._show_zoom_speed_dialog)
        toolbar.addAction(action_zoom_speed)

        # 透明度調整ボタン
        action_transparency = QAction("透明度", self)
        action_transparency.setStatusTip("ウィンドウの透明度を設定")
        action_transparency.triggered.connect(self._show_transparency_dialog)
        toolbar.addAction(action_transparency)
        
        # グリッド表示ボタン
        action_grid = QAction("グリッド", self)
        action_grid.setCheckable(True)
        action_grid.setStatusTip("グリッド表示のON/OFF")
        action_grid.triggered.connect(self._toggle_grid)
        toolbar.addAction(action_grid)
        
        # グリッドスナップボタン
        action_grid_snap = QAction("グリッドスナップ", self)
        action_grid_snap.setCheckable(True)
        action_grid_snap.setStatusTip("ノード移動時のグリッドスナップ")
        action_grid_snap.triggered.connect(self._toggle_grid_snap)
        toolbar.addAction(action_grid_snap)
        
        # 接続線交差解決ボタン
        action_resolve_intersections = QAction("交差解決", self)
        action_resolve_intersections.setStatusTip("接続線の交差を自動解決")
        action_resolve_intersections.triggered.connect(self._resolve_intersections)
        toolbar.addAction(action_resolve_intersections)

        # 削除ボタン（Delete/Backspace両方に対応）
        action_delete = QAction("削除", self)
        action_delete.setStatusTip("選択したノードを削除 (Delete/Backspace)")
        action_delete.setShortcuts([QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)])
        action_delete.triggered.connect(self._delete_selected_nodes)
        toolbar.addAction(action_delete)

        # 保存ボタン
        action_save = QAction("保存", self)
        action_save.setStatusTip("マインドマップをJSONファイルに保存")
        action_save.setShortcut(QKeySequence.Save)
        action_save.triggered.connect(self._save_mindmap)
        toolbar.addAction(action_save)

        # 読み込みボタン
        action_load = QAction("読み込み", self)
        action_load.setStatusTip("JSONファイルからマインドマップを読み込み")
        action_load.setShortcut(QKeySequence.Open)
        action_load.triggered.connect(self._load_mindmap)
        toolbar.addAction(action_load)

        # 将来的な機能拡張のためのプレースホルダ
        # - 保存 / 読み込み
        # - 削除 / 編集

    def _show_zoom_speed_dialog(self):
        """ズームスピード設定ダイアログを表示"""
        current_speed = self.view.get_zoom_speed()
        
        dialog = ZoomSpeedDialog(self, current_speed)
        if dialog.exec() == QDialog.Accepted:
            new_speed = dialog.get_zoom_speed()
            self.view.set_zoom_speed(new_speed)
            percent = (new_speed - 1.0) * 100
            self.statusBar().showMessage(f"ズームスピードを{percent:.1f}%に設定しました", 2000)

    def _show_transparency_dialog(self):
        """透明度設定ダイアログを表示"""
        dialog = TransparencyDialog(
            self, 
            self.view.get_background_transparency(),
            self.view.get_node_transparency(),
            self.view.get_line_transparency()
        )
        if dialog.exec() == QDialog.Accepted:
            bg_transparency = dialog.get_background_transparency()
            node_transparency = dialog.get_node_transparency()
            line_transparency = dialog.get_line_transparency()
            
            self.view.set_background_transparency(bg_transparency)
            self.view.set_node_transparency(node_transparency)
            self.view.set_line_transparency(line_transparency)
            
            self.statusBar().showMessage(
                f"背景:{bg_transparency*100:.0f}% ノード:{node_transparency*100:.0f}% 接続線:{line_transparency*100:.0f}%", 
                3000
            )
    
    def _toggle_grid(self, enabled: bool):
        """グリッド表示の切り替え"""
        self.view.set_grid_enabled(enabled)
        if enabled:
            self.statusBar().showMessage("グリッド表示: ON", 2000)
        else:
            self.statusBar().showMessage("グリッド表示: OFF", 2000)
    
    def _toggle_grid_snap(self, enabled: bool):
        """グリッドスナップの切り替え"""
        self.view.set_grid_snap_enabled(enabled)
        if enabled:
            self.statusBar().showMessage("グリッドスナップ: ON", 2000)
        else:
            self.statusBar().showMessage("グリッドスナップ: OFF", 2000)
    
    def _resolve_intersections(self):
        """接続線の交差を手動で解決"""
        intersections = self.view._check_connection_line_intersections()
        if intersections:
            self.view._resolve_connection_line_intersections()
            self.statusBar().showMessage(f"{len(intersections)}個の接続線交差を解決しました", 3000)
        else:
            self.statusBar().showMessage("接続線の交差はありません", 2000)

    def set_transparency(self, transparency: float):
        """ウィンドウの透明度を設定（0.1-1.0）"""
        if 0.1 <= transparency <= 1.0:
            self.transparency = transparency
            self.setWindowOpacity(transparency)
        else:
            print("透明度は0.1から1.0の範囲で設定してください")

    def get_transparency(self) -> float:
        """現在の透明度を取得"""
        return self.transparency

    def _toggle_connect_mode(self, enabled: bool):
        self.view.connect_mode_enabled = enabled
        if enabled:
            self.statusBar().showMessage("接続モード: Shiftキーを押しながらノードをクリックして接続")
        else:
            self.statusBar().showMessage("通常モード: ノードをドラッグして移動、Shift+クリックで接続")

    def _delete_selected_nodes(self):
        """選択されたノードを削除"""
        self.view._delete_selected_nodes()

    def _save_mindmap(self):
        """マインドマップをJSONファイルに保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "マインドマップを保存", 
            "mindmap.json", 
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                data = self.view._export_to_json()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(data)
                QMessageBox.information(self, "保存完了", f"マインドマップを保存しました:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存エラー", f"保存に失敗しました:\n{str(e)}")

    def _load_mindmap(self):
        """JSONファイルからマインドマップを読み込み"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "マインドマップを読み込み", 
            "", 
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = f.read()
                self.view._import_from_json(data)
                QMessageBox.information(self, "読み込み完了", f"マインドマップを読み込みました:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "読み込みエラー", f"読み込みに失敗しました:\n{str(e)}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()