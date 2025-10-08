"""
テキスト入力機能専用のクラス
"""
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLineEdit,
    QInputDialog,
    QGraphicsProxyWidget,
    QGraphicsTextItem,
)


class CustomLineEdit(QLineEdit):
    """カスタムLineEdit（Escapeキー処理用）"""
    
    def __init__(self, text_editor, parent=None):
        super().__init__(parent)
        self.text_editor = text_editor
    
    def keyPressEvent(self, event):
        """キープレスイベント"""
        if event.key() == Qt.Key_Escape:
            self.text_editor._cancel_editing()
        else:
            # 全てのキーイベントをLineEditで処理
            super().keyPressEvent(event)
    
    def inputMethodEvent(self, event):
        """日本語入力（IME）イベント"""
        # IMEイベントを適切に処理
        super().inputMethodEvent(event)
    
    def focusInEvent(self, event):
        """フォーカスインイベント"""
        super().focusInEvent(event)
        # IMEの準備を確実にする（即座に実行）
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setInputMethodHints(Qt.ImhPreferUppercase | Qt.ImhPreferLowercase)
    
    def focusOutEvent(self, event):
        """フォーカスアウトイベント"""
        super().focusOutEvent(event)


class NodeTextEditor:
    """ノードのテキスト編集機能を管理するクラス"""
    
    def __init__(self, node_item):
        self.node_item = node_item
        self.line_edit: QLineEdit | None = None
        self.proxy_widget: QGraphicsProxyWidget | None = None
        self.is_editing = False
        self.original_text = ""
        
    def start_editing(self):
        """テキスト編集を開始"""
        if self.is_editing:
            return
        
        self.is_editing = True
        self.original_text = self.node_item.text_item.toPlainText()
        
        # プロキシウィジェットを作成
        self.proxy_widget = QGraphicsProxyWidget(self.node_item)
        
        # LineEditを作成
        self.line_edit = CustomLineEdit(self, self.original_text)
        self.line_edit.setFont(QFont("Arial", 12))
        self.line_edit.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 2px solid #0078d4;
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }
        """)
        
        # 日本語入力（IME）の設定
        self.line_edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.line_edit.setInputMethodHints(Qt.ImhPreferUppercase | Qt.ImhPreferLowercase)
        
        # IMEの準備を確実にするための追加設定
        self.line_edit.setAttribute(Qt.WA_KeyCompression, False)
        self.line_edit.setAcceptDrops(False)
        
        # プロキシウィジェットにLineEditを設定
        self.proxy_widget.setWidget(self.line_edit)
        
        # 位置を調整（ノードの中央に配置）
        text_rect = self.node_item.text_item.boundingRect()
        self.proxy_widget.setPos(-text_rect.width() / 2, -text_rect.height() / 2)
        self.proxy_widget.resize(text_rect.width() + 20, text_rect.height() + 10)
        
        # イベント接続
        self.line_edit.returnPressed.connect(self._finish_editing)
        self.line_edit.focusOutEvent = self._line_edit_focus_out
        
        # フォーカスとテキスト選択
        self.line_edit.setFocusPolicy(Qt.StrongFocus)
        
        # フォーカス設定とテキスト選択
        self.line_edit.setFocus()
        self.line_edit.activateWindow()
        QTimer.singleShot(10, self.line_edit.selectAll)
        
        # ノードのテキストを非表示
        self.node_item.text_item.setVisible(False)
    
    
    
    def _finish_editing(self):
        """編集を完了"""
        if not self.is_editing or self.line_edit is None:
            return
        
        new_text = self.line_edit.text().strip()
        if new_text and new_text != self.original_text:
            # テキストが変更された場合
            self.node_item.text_item.setPlainText(new_text)
            self.node_item._update_text_position()
            
            # Undoスタックに追加
            if self.node_item._view.undo_stack is not None:
                from commands import RenameNodeCommand
                self.node_item._view.undo_stack.push(
                    RenameNodeCommand(self.node_item, self.original_text, new_text)
                )
        
        self._cleanup_editing()
    
    def _cancel_editing(self):
        """編集をキャンセル"""
        self._cleanup_editing()
    
    def _line_edit_focus_out(self, event):
        """LineEditのフォーカスアウトイベント"""
        # 少し遅延させてから処理（クリックイベントとの競合を避ける）
        QTimer.singleShot(100, self._finish_editing)
        super(QLineEdit, self.line_edit).focusOutEvent(event)
    
    
    def _cleanup_editing(self):
        """編集状態をクリーンアップ"""
        if self.proxy_widget is not None:
            self.proxy_widget.setWidget(None)
            self.proxy_widget.deleteLater()
            self.proxy_widget = None
        
        if self.line_edit is not None:
            self.line_edit.deleteLater()
            self.line_edit = None
        
        # ノードのテキストを再表示
        self.node_item.text_item.setVisible(True)
        
        self.is_editing = False
        self.original_text = ""


class SimpleTextEditor:
    """シンプルなテキスト編集機能（ダイアログベース）"""
    
    def __init__(self, node_item):
        self.node_item = node_item
    
    def start_editing(self):
        """テキスト編集を開始（ダイアログベース）"""
        current_text = self.node_item.text_item.toPlainText()
        
        new_text, ok = QInputDialog.getText(
            self.node_item._view,
            "ノード名変更",
            "新しいノード名:",
            text=current_text
        )
        
        if ok and new_text.strip() and new_text.strip() != current_text:
            # テキストが変更された場合
            old_text = current_text
            self.node_item.text_item.setPlainText(new_text.strip())
            self.node_item._update_text_position()
            
            # Undoスタックに追加
            if self.node_item._view.undo_stack is not None:
                from commands import RenameNodeCommand
                self.node_item._view.undo_stack.push(
                    RenameNodeCommand(self.node_item, old_text, new_text.strip())
                )

    def update_theme(self, theme: dict):
        """テーマを更新"""
        if self.line_edit and "text_color" in theme and "node_bg" in theme:
            from PySide6.QtGui import QColor
            # LineEditの色を更新
            self.line_edit.setStyleSheet(f"""
                QLineEdit {{
                    color: {theme['text_color']};
                    background-color: {theme['node_bg']};
                    border: 2px solid {theme.get('node_border', '#333333')};
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
