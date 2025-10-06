"""
接続線関連のクラス
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsLineItem


class CrankConnection:
    """
    3段階クランク状の接続線を管理するクラス
    
    このクラスは以下の機能を提供します：
    - ノード間の3段階クランク状接続線の描画（水平→垂直→水平）
    - 接続線の自動更新（ノードの移動に追従）
    - 接続線の削除機能
    - 接続線の視覚的スタイリング
    
    接続線の構成：
    - horizontal_line1: 最初の水平線（ソースノードから）
    - vertical_line: 垂直線（方向転換）
    - horizontal_line2: 2番目の水平線（ターゲットノードへ）
    
    主要なメソッド：
    - _create_crank_lines(): 接続線の作成
    - update_connection(): 接続線の更新
    - remove(): 接続線の削除
    """
    
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
        # 線のスタイル設定
        pen = QPen(Qt.darkGray, 1.0)
        pen.setStyle(Qt.DashLine)
        
        # 3本の線を作成
        self.horizontal_line1 = QGraphicsLineItem()
        self.vertical_line = QGraphicsLineItem()
        self.horizontal_line2 = QGraphicsLineItem()
        
        # スタイルを適用
        for line in [self.horizontal_line1, self.vertical_line, self.horizontal_line2]:
            line.setPen(pen)
            line.setZValue(-1)  # ノードの後ろに表示
        
        # シーンに追加
        self.scene.addItem(self.horizontal_line1)
        self.scene.addItem(self.vertical_line)
        self.scene.addItem(self.horizontal_line2)
        
        # 初期位置を設定
        self.update_connection()
    
    def update_connection(self):
        """接続線の位置を更新"""
        if not all([self.horizontal_line1, self.vertical_line, self.horizontal_line2]):
            return
        
        # ノードの境界を取得
        source_rect = self.source.sceneBoundingRect()
        target_rect = self.target.sceneBoundingRect()
        
        # 接続点を計算（右端と左端）
        start_x = source_rect.right()
        start_y = source_rect.center().y()
        end_x = target_rect.left()
        end_y = target_rect.center().y()
        
        # 垂直線のX位置を統一
        vertical_x = self._get_unified_vertical_x_position()
        
        # horizontal_line2が必ず右方向（プラス方向）に向くように調整
        # ターゲットが垂直線より左にある場合は、ターゲットの右端を使用
        if end_x < vertical_x:
            end_x = target_rect.right()
        
        # さらに、horizontal_line2の終点が垂直線より右にあることを保証
        if end_x <= vertical_x:
            end_x = vertical_x + 30  # 最小距離を確保（20pxから30pxに増加）
        
        # 最終的な方向チェック：horizontal_line2が左向きにならないように
        if end_x < vertical_x:
            end_x = vertical_x + 30
        
        # 3段階の線を設定
        self.horizontal_line1.setLine(start_x, start_y, vertical_x, start_y)
        self.vertical_line.setLine(vertical_x, start_y, vertical_x, end_y)
        self.horizontal_line2.setLine(vertical_x, end_y, end_x, end_y)
    
    def _get_unified_vertical_x_position(self):
        """統一された垂直線のX位置を取得"""
        # 基本位置 + 20の固定オフセット
        return self.source.sceneBoundingRect().right() + 20
    
    def remove(self):
        """接続線を削除"""
        if self.horizontal_line1:
            self.scene.removeItem(self.horizontal_line1)
        if self.vertical_line:
            self.scene.removeItem(self.vertical_line)
        if self.horizontal_line2:
            self.scene.removeItem(self.horizontal_line2)

