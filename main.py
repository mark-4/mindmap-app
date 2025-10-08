"""
マインドマップアプリケーション - メインファイル
"""
import sys
import json
import os
from PySide6.QtCore import QPointF, Qt, QSettings
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
        
        # テーマの初期設定
        self.current_theme = "default"
        self.themes = {
            "default": {
                "name": "デフォルト",
                "background": "#f0f0f0",
                "node_bg": "#ffffff",
                "node_border": "#333333",
                "text_color": "#000000",
                "toolbar_bg": "#e0e0e0",
                "button_bg": "#ffffff",
                "button_hover": "#e0e0e0",
                "button_checked": "#0078d4",
                "button_checked_text": "#ffffff"
            },
            "gray": {
                "name": "目にやさしいグレー",
                "background": "#2b2b2b",
                "node_bg": "#3c3c3c",
                "node_border": "#666666",
                "text_color": "#ffffff",
                "toolbar_bg": "#1e1e1e",
                "button_bg": "#3c3c3c",
                "button_hover": "#4c4c4c",
                "button_checked": "#0078d4",
                "button_checked_text": "#ffffff"
            },
            "pastel": {
                "name": "明るいパステル",
                "background": "#f8f9fa",
                "node_bg": "#ffffff",
                "node_border": "#e1e5e9",
                "text_color": "#2c3e50",
                "toolbar_bg": "#e9ecef",
                "button_bg": "#ffffff",
                "button_hover": "#f1f3f4",
                "button_checked": "#6c5ce7",
                "button_checked_text": "#ffffff"
            }
        }

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
            QToolButton:checked { 
                background: rgba(100, 150, 255, 180); 
                border: 2px solid rgba(50, 100, 200, 200); 
                color: white; 
            }
            QToolButton:checked:hover { 
                background: rgba(120, 170, 255, 200); 
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
        
        # ツールバーの設定を復元（アクション順番のみ）
        self._restore_toolbar_actions_only()

    def _create_toolbar(self):
        """ツールバーを作成"""
        toolbar = QToolBar("Tools", self)
        
        # ツールバーのドラッグ&ドロップ機能を有効にする
        toolbar.setMovable(True)  # ツールバー自体の移動を有効
        toolbar.setFloatable(True)  # ツールバーの浮動化を有効
        
        # ツールバー内のアクションのドラッグ&ドロップを有効にする
        toolbar.setAllowedAreas(Qt.TopToolBarArea | Qt.BottomToolBarArea | Qt.LeftToolBarArea | Qt.RightToolBarArea)
        
        # ツールバー内のウィジェットのドラッグ&ドロップを有効にする
        toolbar.setContextMenuPolicy(Qt.CustomContextMenu)
        toolbar.customContextMenuRequested.connect(self._show_toolbar_context_menu)
        
        self.addToolBar(toolbar)

        # Undo/Redo アクション
        undo_action = self.undo_stack.createUndoAction(self, "取り消し")
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setObjectName("undo_action")
        redo_action = self.undo_stack.createRedoAction(self, "やり直し")
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.setObjectName("redo_action")
        toolbar.addAction(undo_action)
        toolbar.addAction(redo_action)

        # ノード追加
        action_add = QAction("ノード追加", self)
        action_add.setStatusTip("新しいノードを中央に追加 (Tabキー)")
        action_add.setShortcut(QKeySequence(Qt.Key_Tab))
        action_add.setObjectName("add_node_action")
        action_add.triggered.connect(self._add_node)
        toolbar.addAction(action_add)

        # キューブノード追加

        # 全選択
        action_select_all = QAction("全選択", self)
        action_select_all.setStatusTip("全てのノードを選択 (Cmd+A)")
        action_select_all.setShortcut(QKeySequence.SelectAll)
        action_select_all.setObjectName("select_all_action")
        action_select_all.triggered.connect(self.view._select_all_nodes)
        toolbar.addAction(action_select_all)

        # 接続モード
        action_connect = QAction("接続モード", self)
        action_connect.setCheckable(True)
        action_connect.setChecked(False)
        action_connect.setStatusTip("Shiftキーを押しながらノードをクリックして接続")
        action_connect.setObjectName("connect_mode_action")
        action_connect.toggled.connect(self._toggle_connect_mode)
        toolbar.addAction(action_connect)

        # フィット
        action_fit = QAction("フィット", self)
        action_fit.setStatusTip("全てのノードが画面に収まるように調整")
        action_fit.setObjectName("fit_action")
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

        # アピアランス
        action_appearance = QAction("アピアランス", self)
        action_appearance.setStatusTip("UI配色テーマを選択")
        action_appearance.triggered.connect(self._show_appearance_menu)
        toolbar.addAction(action_appearance)

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
        action_align.setObjectName("align_action")
        action_align.triggered.connect(self.view.align_generations_and_avoid_line_overlap)
        toolbar.addAction(action_align)

        # 削除
        action_delete = QAction("削除", self)
        action_delete.setStatusTip("選択されたノードを削除")
        action_delete.setShortcuts([QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)])
        action_delete.setObjectName("delete_action")
        action_delete.triggered.connect(self._delete_selected_nodes)
        toolbar.addAction(action_delete)

        # 保存
        action_save = QAction("保存", self)
        action_save.setStatusTip("マインドマップを保存")
        action_save.setShortcut(QKeySequence.Save)
        action_save.setObjectName("save_action")
        action_save.triggered.connect(self._save_mindmap)
        toolbar.addAction(action_save)

        # 読み込み
        action_load = QAction("読み込み", self)
        action_load.setStatusTip("マインドマップを読み込み")
        action_load.setShortcut(QKeySequence.Open)
        action_load.setObjectName("load_action")
        action_load.triggered.connect(self._load_mindmap)
        toolbar.addAction(action_load)
        
        # ツールバーの参照を保存
        self.toolbar = toolbar

    def _save_toolbar_state(self):
        """ツールバーの状態を保存（アクション順番のみ）"""
        try:
            settings = QSettings("MindMapApp", "ToolbarSettings")
            
            # アクションの順番を保存
            action_order = []
            for action in self.toolbar.actions():
                if action.objectName():
                    action_order.append(action.objectName())
            
            settings.setValue("action_order", action_order)
            
        except Exception as e:
            print(f"ツールバー状態の保存エラー: {e}")

    def _restore_toolbar_state(self):
        """ツールバーの状態を復元"""
        try:
            settings = QSettings("MindMapApp", "ToolbarSettings")
            
            # アクションの順番を復元
            action_order = settings.value("action_order", [])
            if action_order:
                self._reorder_toolbar_actions(action_order)
            
            # ジオメトリと位置を復元
            toolbar_geometry = settings.value("toolbar_geometry")
            if toolbar_geometry:
                self.toolbar.restoreGeometry(toolbar_geometry)
            
            # 浮動状態を復元
            is_floating = settings.value("toolbar_floating", False, type=bool)
            if is_floating:
                self.toolbar.setFloating(True)
            
            # ツールバーエリアを復元（安全に）
            try:
                toolbar_area = settings.value("toolbar_area", Qt.TopToolBarArea, type=int)
                if toolbar_area in [Qt.TopToolBarArea, Qt.BottomToolBarArea, Qt.LeftToolBarArea, Qt.RightToolBarArea]:
                    # 既存のツールバーを削除してから新しいエリアに追加
                    self.removeToolBar(self.toolbar)
                    self.addToolBar(Qt.ToolBarArea(toolbar_area), self.toolbar)
            except Exception as area_error:
                print(f"ツールバーエリア復元エラー: {area_error}")
                # エラーの場合はデフォルトの上部エリアに配置
                pass
            
        except Exception as e:
            print(f"ツールバー状態の復元エラー: {e}")

    def _restore_toolbar_actions_only(self):
        """ツールバーのアクション順番のみを復元（安全版）"""
        try:
            settings = QSettings("MindMapApp", "ToolbarSettings")
            action_order = settings.value("action_order", [])
            if action_order:
                self._reorder_toolbar_actions(action_order)
        except Exception as e:
            print(f"ツールバーアクション復元エラー: {e}")

    def _reorder_toolbar_actions(self, action_order):
        """ツールバーのアクションを指定された順番に並べ替え"""
        try:
            # 現在のアクションを取得
            current_actions = self.toolbar.actions()
            
            # アクションを名前でマッピング
            action_map = {}
            for action in current_actions:
                if action.objectName():
                    action_map[action.objectName()] = action
            
            # 新しい順番でアクションを再作成
            new_actions = []
            for action_name in action_order:
                if action_name in action_map:
                    action = action_map[action_name]
                    # アクションの情報を保存
                    new_actions.append({
                        'text': action.text(),
                        'object_name': action.objectName(),
                        'checkable': action.isCheckable(),
                        'checked': action.isChecked(),
                        'shortcut': action.shortcut(),
                        'status_tip': action.statusTip()
                    })
            
            # 順番に含まれていないアクションも追加
            for action in current_actions:
                if action.objectName() and action.objectName() not in action_order:
                    new_actions.append({
                        'text': action.text(),
                        'object_name': action.objectName(),
                        'checkable': action.isCheckable(),
                        'checked': action.isChecked(),
                        'shortcut': action.shortcut(),
                        'status_tip': action.statusTip()
                    })
            
            # ツールバーを完全に再作成
            self.removeToolBar(self.toolbar)
            self._create_toolbar_with_order(new_actions)
                    
        except Exception as e:
            print(f"ツールバーアクション並べ替えエラー: {e}")

    def _create_toolbar_with_order(self, action_data_list):
        """指定された順番でツールバーを作成"""
        try:
            # 新しいツールバーを作成
            toolbar = QToolBar("Tools", self)
            
            # ツールバーのドラッグ&ドロップ機能を有効にする
            toolbar.setMovable(True)
            toolbar.setFloatable(True)
            toolbar.setAllowedAreas(Qt.TopToolBarArea | Qt.BottomToolBarArea | Qt.LeftToolBarArea | Qt.RightToolBarArea)
            toolbar.setContextMenuPolicy(Qt.CustomContextMenu)
            toolbar.customContextMenuRequested.connect(self._show_toolbar_context_menu)
            
            self.addToolBar(toolbar)
            
            # アクションを順番に追加
            for action_data in action_data_list:
                if 'separator' in action_data and action_data['separator']:
                    # セパレーターを追加
                    toolbar.addSeparator()
                else:
                    # 通常のアクションを追加
                    action = QAction(action_data['text'], self)
                    action.setObjectName(action_data['object_name'])
                    action.setCheckable(action_data['checkable'])
                    action.setChecked(action_data['checked'])
                    action.setShortcut(action_data['shortcut'])
                    action.setStatusTip(action_data['status_tip'])
                    
                    # アクションの接続を復元
                    self._connect_action(action)
                    
                    toolbar.addAction(action)
            
            # ツールバーの参照を更新
            self.toolbar = toolbar
            
        except Exception as e:
            print(f"ツールバー作成エラー: {e}")

    def _connect_action(self, action):
        """アクションの接続を復元"""
        try:
            object_name = action.objectName()
            
            if object_name == "undo_action":
                action.triggered.connect(self.undo_stack.undo)
            elif object_name == "redo_action":
                action.triggered.connect(self.undo_stack.redo)
            elif object_name == "add_node_action":
                action.triggered.connect(self._add_node)
            elif object_name == "select_all_action":
                action.triggered.connect(self.view._select_all_nodes)
            elif object_name == "connect_mode_action":
                action.toggled.connect(self._toggle_connect_mode)
            elif object_name == "fit_action":
                action.triggered.connect(self.view.fit_all_nodes)
            elif object_name == "auto_fit_action":
                action.toggled.connect(self._toggle_auto_fit)
            elif object_name == "attraction_action":
                action.toggled.connect(self._toggle_attraction)
            elif object_name == "zoom_speed_action":
                action.triggered.connect(self._show_zoom_speed_dialog)
            elif object_name == "transparency_action":
                action.triggered.connect(self._show_transparency_dialog)
            elif object_name == "appearance_action":
                action.triggered.connect(self._show_appearance_menu)
            elif object_name == "grid_action":
                action.toggled.connect(self._toggle_grid)
            elif object_name == "grid_snap_action":
                action.toggled.connect(self._toggle_grid_snap)
            elif object_name == "align_action":
                action.triggered.connect(self.view.align_generations_and_avoid_line_overlap)
            elif object_name == "delete_action":
                action.triggered.connect(self._delete_selected_nodes)
            elif object_name == "save_action":
                action.triggered.connect(self._save_mindmap)
            elif object_name == "load_action":
                action.triggered.connect(self._load_mindmap)
                
        except Exception as e:
            print(f"アクション接続エラー: {e}")

    def _show_toolbar_context_menu(self, position):
        """ツールバーの右クリックメニューを表示"""
        try:
            from PySide6.QtWidgets import QMenu
            
            menu = QMenu(self)
            
            # ツールバーリセット
            reset_action = menu.addAction("ツールバーをリセット")
            reset_action.triggered.connect(self._reset_toolbar)
            
            # アクション順番変更
            reorder_action = menu.addAction("ボタン順番を変更")
            reorder_action.triggered.connect(self._show_reorder_dialog)
            
            # メニューを表示
            menu.exec(self.toolbar.mapToGlobal(position))
            
        except Exception as e:
            print(f"ツールバーコンテキストメニューエラー: {e}")

    def _reset_toolbar(self):
        """ツールバーをデフォルト状態にリセット"""
        try:
            # 設定をクリア
            settings = QSettings("MindMapApp", "ToolbarSettings")
            settings.clear()
            
            # ツールバーを完全に再作成
            self.removeToolBar(self.toolbar)
            self._create_toolbar()
            
            print("ツールバーをリセットしました")
            
        except Exception as e:
            print(f"ツールバーリセットエラー: {e}")

    def _show_reorder_dialog(self):
        """ボタン順番変更ダイアログを表示"""
        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel
            
            dialog = QDialog(self)
            dialog.setWindowTitle("ツールバーボタンの順番変更")
            dialog.setModal(True)
            dialog.resize(400, 300)
            
            layout = QVBoxLayout(dialog)
            
            # 説明ラベル
            label = QLabel("ボタンの順番を変更してください（上に移動・下に移動ボタンを使用）:")
            layout.addWidget(label)
            
            # リストウィジェット
            list_widget = QListWidget()
            current_actions = self.toolbar.actions()
            
            print(f"ツールバー内のアクション数: {len(current_actions)}")
            
            for i, action in enumerate(current_actions):
                print(f"アクション {i}: text='{action.text()}', objectName='{action.objectName()}', isSeparator={action.isSeparator()}")
                
                # セパレーターでないアクションのみを表示
                if not action.isSeparator():
                    display_text = action.text() if action.text() else f"アクション {i}"
                    list_widget.addItem(display_text)
            
            print(f"リストに追加されたアイテム数: {list_widget.count()}")
            layout.addWidget(list_widget)
            
            # ボタンレイアウト
            button_layout = QHBoxLayout()
            
            up_button = QPushButton("上に移動")
            up_button.clicked.connect(lambda: self._move_item_up(list_widget))
            button_layout.addWidget(up_button)
            
            down_button = QPushButton("下に移動")
            down_button.clicked.connect(lambda: self._move_item_down(list_widget))
            button_layout.addWidget(down_button)
            
            button_layout.addStretch()
            
            ok_button = QPushButton("OK")
            ok_button.clicked.connect(lambda: self._apply_reorder(list_widget, dialog))
            button_layout.addWidget(ok_button)
            
            cancel_button = QPushButton("キャンセル")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            layout.addLayout(button_layout)
            
            dialog.exec()
            
        except Exception as e:
            print(f"順番変更ダイアログエラー: {e}")

    def _move_item_up(self, list_widget):
        """リストアイテムを上に移動"""
        current_row = list_widget.currentRow()
        if current_row > 0:
            item = list_widget.takeItem(current_row)
            list_widget.insertItem(current_row - 1, item)
            list_widget.setCurrentRow(current_row - 1)

    def _move_item_down(self, list_widget):
        """リストアイテムを下に移動"""
        current_row = list_widget.currentRow()
        if current_row < list_widget.count() - 1:
            item = list_widget.takeItem(current_row)
            list_widget.insertItem(current_row + 1, item)
            list_widget.setCurrentRow(current_row + 1)

    def _apply_reorder(self, list_widget, dialog):
        """新しい順番を適用"""
        try:
            # 現在のアクションを取得
            current_actions = self.toolbar.actions()
            
            # 新しい順番を取得
            new_order = []
            for i in range(list_widget.count()):
                new_order.append(list_widget.item(i).text())
            
            print(f"新しい順番: {new_order}")
            
            # アクション名のマッピング（テキストからobjectNameへ）
            action_name_map = {
                "取り消し": "undo_action",
                "やり直し": "redo_action", 
                "ノード追加": "add_node_action",
                "全選択": "select_all_action",
                "接続モード": "connect_mode_action",
                "フィット": "fit_action",
                "オートフィット": "auto_fit_action",
                "アトラクション": "attraction_action",
                "ズーム速度": "zoom_speed_action",
                "透明度": "transparency_action",
                "アピアランス": "appearance_action",
                "グリッド": "grid_action",
                "グリッドスナップ": "grid_snap_action",
                "整理": "align_action",
                "削除": "delete_action",
                "保存": "save_action",
                "読み込み": "load_action"
            }
            
            # 現在のアクションをテキストでマッピング
            current_action_map = {}
            for action in current_actions:
                if not action.isSeparator() and action.text():
                    current_action_map[action.text()] = action
            
            # 新しい順番でアクションを再作成
            new_actions = []
            for text in new_order:
                if text in current_action_map:
                    action = current_action_map[text]
                    # アクションの情報を保存
                    new_actions.append({
                        'text': action.text(),
                        'object_name': action.objectName(),
                        'checkable': action.isCheckable(),
                        'checked': action.isChecked(),
                        'shortcut': action.shortcut(),
                        'status_tip': action.statusTip()
                    })
            
            # セパレーターを適切な位置に挿入
            new_actions_with_separators = []
            for i, action_data in enumerate(new_actions):
                new_actions_with_separators.append(action_data)
                # 特定の位置にセパレーターを挿入
                if i in [1, 3, 5, 7, 9, 11, 13]:  # 適切な位置にセパレーターを挿入
                    new_actions_with_separators.append({'separator': True})
            
            # ツールバーを完全に再作成
            self.removeToolBar(self.toolbar)
            self._create_toolbar_with_order(new_actions_with_separators)
            
            # 設定を保存
            self._save_toolbar_state()
            
            dialog.accept()
            print("ツールバーの順番を変更しました")
            
        except Exception as e:
            print(f"順番適用エラー: {e}")

    def _create_toolbar_actions(self):
        """ツールバーのアクションを作成（リセット用）"""
        # 既存のアクションを再追加
        # この部分は元の_create_toolbarメソッドの内容を再利用
        pass

    def closeEvent(self, event):
        """アプリケーション終了時の処理"""
        # ツールバーの状態を保存
        self._save_toolbar_state()
        event.accept()

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

    def _show_appearance_menu(self):
        """アピアランスメニューを表示"""
        from PySide6.QtWidgets import QMenu
        
        menu = QMenu(self)
        
        # 各テーマのアクションを作成
        for theme_id, theme_data in self.themes.items():
            action = QAction(theme_data["name"], self)
            action.setCheckable(True)
            action.setChecked(theme_id == self.current_theme)
            action.triggered.connect(lambda checked, tid=theme_id: self._change_theme(tid))
            menu.addAction(action)
        
        # メニューを表示（マウスカーソル位置に表示）
        menu.exec(self.cursor().pos())

    def _change_theme(self, theme_id: str):
        """テーマを変更"""
        if theme_id not in self.themes:
            return
        
        self.current_theme = theme_id
        theme = self.themes[theme_id]
        
        # スタイルシートを適用
        stylesheet = f"""
        QMainWindow {{
            background-color: {theme['background']};
        }}
        QToolBar {{
            background-color: {theme['toolbar_bg']};
            border: none;
            spacing: 3px;
        }}
        QToolButton {{
            background-color: {theme['button_bg']};
            border: 1px solid {theme['node_border']};
            border-radius: 4px;
            padding: 4px 8px;
            color: {theme['text_color']};
        }}
        QToolButton:hover {{
            background-color: {theme['button_hover']};
        }}
        QToolButton:checked {{
            background-color: {theme['button_checked']};
            color: {theme['button_checked_text']};
            border: 2px solid {theme['button_checked']};
        }}
        QStatusBar {{
            background-color: {theme['toolbar_bg']};
            color: {theme['text_color']};
        }}
        """
        
        self.setStyleSheet(stylesheet)
        
        # ビューにもテーマ情報を渡す
        self.view.set_theme(theme)
        
        self.statusBar().showMessage(f"テーマを「{theme['name']}」に変更しました", 2000)


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
