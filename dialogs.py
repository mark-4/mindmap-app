"""
ダイアログ関連のクラス
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QLabel,
    QPushButton,
)


class ZoomSpeedDialog(QDialog):
    """
    ズーム速度設定ダイアログクラス
    
    このクラスは以下の機能を提供します：
    - ズーム速度の設定UI
    - スライダーによる速度調整（1-200の範囲）
    - 現在の速度の表示（パーセンテージ）
    - 設定値の取得機能
    
    主要なメソッド：
    - _on_slider_changed(): スライダー値変更時の処理
    - get_zoom_speed(): 設定されたズーム速度の取得
    """
    
    def __init__(self, parent=None, current_speed=1.20):
        super().__init__(parent)
        self.setWindowTitle("ズーム速度設定")
        self.setModal(True)
        self.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # スライダー
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)  # 0.1% (0.1%刻み)
        self.slider.setMaximum(200)  # 20% (0.1%刻み)
        # 中央を100%にするため、スライダー値200が100%になるように調整
        # デフォルト20%はスライダー値200に対応（現在の中央値が最大100%）
        slider_value = int((current_speed - 1.0) * 1000)  # 20% = スライダー値200
        self.slider.setValue(slider_value)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)
        
        # パーセント表示ラベル
        self.percent_label = QLabel()
        self._on_slider_changed(self.slider.value())
        layout.addWidget(self.percent_label)
        
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
        # スライダー値200が100%として表示されるように調整（現在の20%が最大100%に対応）
        percent = (value / 200.0) * 100.0  # スライダー値200で100%として表示
        self.percent_label.setText(f"{percent:.1f}%")
    
    def get_zoom_speed(self):
        """設定されたズーム速度を取得"""
        # 実際のズーム速度は変更せず、表示のみ調整
        percent = self.slider.value() * 0.1  # スライダー値200で20%の実際の速度
        return 1.0 + (percent / 100.0)


class TransparencyDialog(QDialog):
    """
    透明度設定ダイアログクラス
    
    このクラスは以下の機能を提供します：
    - ノードの透明度設定UI
    - スライダーによる透明度調整（0-255の範囲）
    - 現在の透明度の表示（パーセンテージ）
    - 設定値の取得機能
    
    主要なメソッド：
    - _on_slider_changed(): スライダー値変更時の処理
    - get_transparency(): 設定された透明度の取得
    """
    
    def __init__(self, parent=None, bg_transparency=1.0, node_transparency=1.0, line_transparency=1.0):
        super().__init__(parent)
        self.setWindowTitle("透明度設定")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # 背景透明度
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("背景透明度:"))
        self.bg_slider = QSlider(Qt.Horizontal)
        self.bg_slider.setMinimum(0)
        self.bg_slider.setMaximum(100)
        self.bg_slider.setValue(int(bg_transparency * 100))
        self.bg_slider.valueChanged.connect(self._on_bg_slider_changed)
        bg_layout.addWidget(self.bg_slider)
        self.bg_label = QLabel(f"{int(bg_transparency * 100)}%")
        bg_layout.addWidget(self.bg_label)
        layout.addLayout(bg_layout)
        
        # ノード透明度
        node_layout = QHBoxLayout()
        node_layout.addWidget(QLabel("ノード透明度:"))
        self.node_slider = QSlider(Qt.Horizontal)
        self.node_slider.setMinimum(10)
        self.node_slider.setMaximum(100)
        self.node_slider.setValue(int(node_transparency * 100))
        self.node_slider.valueChanged.connect(self._on_node_slider_changed)
        node_layout.addWidget(self.node_slider)
        self.node_label = QLabel(f"{int(node_transparency * 100)}%")
        node_layout.addWidget(self.node_label)
        layout.addLayout(node_layout)
        
        # 接続線透明度
        line_layout = QHBoxLayout()
        line_layout.addWidget(QLabel("接続線透明度:"))
        self.line_slider = QSlider(Qt.Horizontal)
        self.line_slider.setMinimum(10)
        self.line_slider.setMaximum(100)
        self.line_slider.setValue(int(line_transparency * 100))
        self.line_slider.valueChanged.connect(self._on_line_slider_changed)
        line_layout.addWidget(self.line_slider)
        self.line_label = QLabel(f"{int(line_transparency * 100)}%")
        line_layout.addWidget(self.line_label)
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
        self.setLayout(layout)
    
    def _on_bg_slider_changed(self, value):
        """背景透明度スライダー変更"""
        self.bg_label.setText(f"{value}%")
    
    def _on_node_slider_changed(self, value):
        """ノード透明度スライダー変更"""
        self.node_label.setText(f"{value}%")
    
    def _on_line_slider_changed(self, value):
        """接続線透明度スライダー変更"""
        self.line_label.setText(f"{value}%")
    
    def get_background_transparency(self):
        """背景透明度を取得"""
        return self.bg_slider.value() / 100.0
    
    def get_node_transparency(self):
        """ノード透明度を取得"""
        return self.node_slider.value() / 100.0
    
    def get_line_transparency(self):
        """接続線透明度を取得"""
        return self.line_slider.value() / 100.0
