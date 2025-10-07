"""
マインドマップアプリケーション - メインファイル
"""
import sys
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QToolBar,
    QFileDialog,
    QMessageBox,
    QDialog,
)

from view import MindMapView
from dialogs import ZoomSpeedDialog, TransparencyDialog


class MainWindow(QMainWindow):
    """
    マインドマップアプリケーションのメインウィンドウクラス
    
    このクラスは以下の機能を提供します：
    - アプリケーションのメインウィンドウの管理
    - ツールバーとメニューの設定
    - ノードの追加・削除・編集機能
    - ズーム・透明度・グリッドの設定
    - ファイルの保存・読み込み機能
    - アンドゥ・リドゥ機能の管理
    
    主要なメソッド：
    - _add_node(): ノードの追加処理
    - _delete_selected_nodes(): 選択されたノードの削除
    - _toggle_grid(): グリッドの表示切り替え
    - _set_zoom_speed(): ズーム速度の設定
    - _set_transparency(): 透明度の設定
    """
    """メインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mind Map (PySide6)")
        self.resize(1100, 750)
        
        # 透明度の初期設定
        self.transparency = 1.0

        self.view = MindMapView(self)
        self.setCentralWidget(self.view)
        
        # macOS用の背景透明化設定
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        
        # ウィンドウのスタイルシートも設定（OSのデスクトップが透けて見えるように）
        self.setStyleSheet("""
            QMainWindow { 
                background: transparent; 
                border: none; 
            }
            QToolBar { 
                background: rgba(240, 240, 240, 150); 
                border: none; 
                border-radius: 5px; 
            }
            QToolButton { 
                background: rgba(255, 255, 255, 100); 
                border: 1px solid rgba(200, 200, 200, 60); 
                border-radius: 3px; 
                padding: 5px; 
            }
            QToolButton:hover { 
                background: rgba(255, 255, 255, 150); 
            }
            QToolButton:pressed { 
                background: rgba(200, 200, 200, 150); 
            }
        """)
        
        # ビューにフォーカスを設定
        self.view.setFocusPolicy(Qt.StrongFocus)
        self.view.setFocus()

        # Undoスタック
        from PySide6.QtGui import QUndoStack
        self.undo_stack = QUndoStack(self)
        self.view.undo_stack = self.undo_stack

        # 中心ノード（起動時に選択状態）
        center_node = self.view.add_node("中心テーマ", QPointF(0, 0))
        center_node.setSelected(True)
        
        # 背景を透明に設定
        self.view.set_background_transparency(0.0)
        
        # ツールバー
        self._create_toolbar()

    def _create_toolbar(self):
        """ツールバーを作成"""
        toolbar = QToolBar("Tools", self)
        self.addToolBar(toolbar)

        # Undo/Redo アクション
        undo_action = self.undo_stack.createUndoAction(self, "取り消し")
        undo_action.setShortcut(QKeySequence.Undo)
        redo_action = self.undo_stack.createRedoAction(self, "やり直し")
        redo_action.setShortcut(QKeySequence.Redo)
        toolbar.addAction(undo_action)
        toolbar.addAction(redo_action)

        # ノード追加
        action_add = QAction("ノード追加", self)
        action_add.setStatusTip("新しいノードを中央に追加 (Tabキー)")
        action_add.setShortcut(QKeySequence(Qt.Key_Tab))
        action_add.triggered.connect(self._add_node)
        toolbar.addAction(action_add)

        # キューブノード追加

        # 全選択
        action_select_all = QAction("全選択", self)
        action_select_all.setStatusTip("全てのノードを選択 (Cmd+A)")
        action_select_all.setShortcut(QKeySequence.SelectAll)
        action_select_all.triggered.connect(self.view._select_all_nodes)
        toolbar.addAction(action_select_all)

        # 接続モード
        action_connect = QAction("接続モード", self)
        action_connect.setCheckable(True)
        action_connect.setChecked(False)
        action_connect.setStatusTip("Shiftキーを押しながらノードをクリックして接続")
        action_connect.toggled.connect(self._toggle_connect_mode)
        toolbar.addAction(action_connect)

        # フィット
        action_fit = QAction("フィット", self)
        action_fit.setStatusTip("全てのノードが画面に収まるように調整")
        action_fit.triggered.connect(self.view.fit_all_nodes)
        toolbar.addAction(action_fit)

        # オートフィット
        action_auto_fit = QAction("オートフィット", self)
        action_auto_fit.setCheckable(True)
        action_auto_fit.setChecked(False)
        action_auto_fit.setStatusTip("ノード追加時に自動的に画面に収まるように調整")
        action_auto_fit.toggled.connect(self._toggle_auto_fit)
        toolbar.addAction(action_auto_fit)

        # アトラクション
        action_attraction = QAction("アトラクション", self)
        action_attraction.setCheckable(True)
        action_attraction.setChecked(False)
        action_attraction.setStatusTip("全てのノードをランダムに動かす (ESCで終了)")
        action_attraction.toggled.connect(self._toggle_attraction)
        toolbar.addAction(action_attraction)

        # ズーム速度
        action_zoom_speed = QAction("ズーム速度", self)
        action_zoom_speed.setStatusTip("ズーム速度を調整")
        action_zoom_speed.triggered.connect(self._show_zoom_speed_dialog)
        toolbar.addAction(action_zoom_speed)

        # 透明度
        action_transparency = QAction("透明度", self)
        action_transparency.setStatusTip("透明度を調整")
        action_transparency.triggered.connect(self._show_transparency_dialog)
        toolbar.addAction(action_transparency)

        # グリッド
        action_grid = QAction("グリッド", self)
        action_grid.setCheckable(True)
        action_grid.setStatusTip("グリッドの表示/非表示")
        action_grid.toggled.connect(self._toggle_grid)
        toolbar.addAction(action_grid)

        # グリッドスナップ
        action_grid_snap = QAction("グリッドスナップ", self)
        action_grid_snap.setCheckable(True)
        action_grid_snap.setChecked(True)  # デフォルトでオン
        action_grid_snap.setStatusTip("グリッドスナップのON/OFF")
        action_grid_snap.toggled.connect(self._toggle_grid_snap)
        toolbar.addAction(action_grid_snap)

        # 整理（整列）
        action_align = QAction("整理", self)
        action_align.setStatusTip("同世代の左端Xを揃え、接続線の重なりを回避")
        action_align.triggered.connect(self.view.align_generations_and_avoid_line_overlap)
        toolbar.addAction(action_align)

        # 削除
        action_delete = QAction("削除", self)
        action_delete.setStatusTip("選択されたノードを削除")
        action_delete.setShortcuts([QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)])
        action_delete.triggered.connect(self._delete_selected_nodes)
        toolbar.addAction(action_delete)

        # 保存
        action_save = QAction("保存", self)
        action_save.setStatusTip("マインドマップを保存")
        action_save.setShortcut(QKeySequence.Save)
        action_save.triggered.connect(self._save_mindmap)
        toolbar.addAction(action_save)

        # 読み込み
        action_load = QAction("読み込み", self)
        action_load.setStatusTip("マインドマップを読み込み")
        action_load.setShortcut(QKeySequence.Open)
        action_load.triggered.connect(self._load_mindmap)
        toolbar.addAction(action_load)

    def _add_node(self):
        """ノードを追加"""
        from commands import AddNodeCommand
        
        parent_node = None
        new_pos = None
        is_parent_node = False
        
        # 選択されたノードがあれば親ノードとして使用
        from node import NodeItem
        selected = [it for it in self.view.scene.selectedItems() if isinstance(it, NodeItem)]
        if selected:
            parent_node = selected[0]
            new_pos = self.view._calculate_smart_position(parent_node)
            is_parent_node = False
        else:
            new_pos = self.view._calculate_parent_node_position()
            is_parent_node = True
        
        self.undo_stack.push(AddNodeCommand(self.view, "新規ノード", parent_node, new_pos, is_parent_node))


    def _toggle_connect_mode(self, enabled: bool):
        """接続モードの切り替え"""
        self.view.connect_mode_enabled = enabled
        if enabled:
            self.statusBar().showMessage("接続モード: Shiftキーを押しながらノードをクリックして接続")
        else:
            self.statusBar().showMessage("接続モード: OFF")

    def _show_zoom_speed_dialog(self):
        """ズーム速度設定ダイアログを表示"""
        dialog = ZoomSpeedDialog(self, self.view.get_zoom_speed())
        if dialog.exec() == QDialog.Accepted:
            new_speed = dialog.get_zoom_speed()
            self.view.set_zoom_speed(new_speed)

    def _show_transparency_dialog(self):
        """透明度設定ダイアログを表示"""
        dialog = TransparencyDialog(
            self,
            self.view.get_background_transparency(),
            self.view.get_node_transparency(),
            self.view.get_line_transparency(),
            self.view.get_window_transparency()
        )
        if dialog.exec() == QDialog.Accepted:
            self.view.set_background_transparency(dialog.get_background_transparency())
            self.view.set_node_transparency(dialog.get_node_transparency())
            self.view.set_line_transparency(dialog.get_line_transparency())
            # ウィンドウ全体の透明度も設定
            self.view.set_window_transparency(dialog.get_window_transparency())

    def _toggle_grid(self, enabled: bool):
        """グリッドの切り替え"""
        self.view.set_grid_enabled(enabled)

    def _toggle_grid_snap(self, enabled: bool):
        """グリッドスナップの切り替え"""
        self.view.set_grid_snap_enabled(enabled)

    def _toggle_auto_fit(self, enabled: bool):
        """オートフィットの切り替え"""
        self.view.set_auto_fit_enabled(enabled)
        if enabled:
            self.statusBar().showMessage("オートフィット: ON - ノード追加時に自動的に画面に収まるように調整")
        else:
            self.statusBar().showMessage("オートフィット: OFF")

    def _toggle_attraction(self, enabled: bool):
        """アトラクションの切り替え"""
        if enabled:
            self.view.start_attraction_mode()
            self.statusBar().showMessage("アトラクション: ON - 全てのノードがランダムに動きます (ESCで終了)")
        else:
            self.view.stop_attraction_mode()
            self.statusBar().showMessage("アトラクション: OFF")

    def _delete_selected_nodes(self):
        """選択されたノードを削除"""
        self.view._delete_selected_nodes()

    def _save_mindmap(self):
        """マインドマップを保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "マインドマップを保存",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                json_data = self.view._export_to_json()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_data)
                self.statusBar().showMessage(f"保存しました: {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"保存に失敗しました: {e}")

    def _load_mindmap(self):
        """マインドマップを読み込み"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "マインドマップを読み込み",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                self.view._import_from_json(json_data)
                self.statusBar().showMessage(f"読み込みました: {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"読み込みに失敗しました: {e}")


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
