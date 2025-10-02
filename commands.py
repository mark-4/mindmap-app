"""
Undo/Redoコマンド
"""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand


class AddNodeCommand(QUndoCommand):
    """
    ノード追加のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードの追加操作のアンドゥ・リドゥ対応
    - 親ノードと子ノードの両方に対応
    - ノード間の接続線の自動作成
    - ノードの位置計算と配置
    
    主要なメソッド：
    - redo(): ノードの追加実行
    - undo(): ノードの追加取り消し
    """
    
    def __init__(self, view: 'MindMapView', label: str = "新規ノード", parent_node: 'NodeItem' = None, pos: QPointF = None, is_parent_node: bool = False):
        super().__init__("ノード追加")
        self.view = view
        self.label = label
        self.parent_node = parent_node
        self.pos = pos
        self.is_parent_node = is_parent_node
        self.node: 'NodeItem' | None = None
        self.connection: 'CrankConnection' | None = None
    
    def redo(self):
        """ノードを追加"""
        self.node = self.view.add_node(self.label, self.pos, self.is_parent_node)
        if self.parent_node is not None:
            self.connection = self.view._create_edge(self.parent_node, self.node)
    
    def undo(self):
        """ノードを削除"""
        if self.connection is not None:
            self.view.remove_edge(self.connection, self.parent_node, self.node)
        if self.node is not None:
            self.view.scene.removeItem(self.node)


class ConnectNodesCommand(QUndoCommand):
    """
    ノード接続のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノード間の接続線作成のアンドゥ・リドゥ対応
    - 接続線の作成と削除
    - 接続線の状態管理
    
    主要なメソッド：
    - redo(): 接続線の作成実行
    - undo(): 接続線の作成取り消し
    """
    
    def __init__(self, view: 'MindMapView', source: 'NodeItem', target: 'NodeItem'):
        super().__init__("ノード接続")
        self.view = view
        self.source = source
        self.target = target
        self.connection: 'CrankConnection' | None = None
    
    def redo(self):
        """接続を作成"""
        self.connection = self.view._create_edge(self.source, self.target)
    
    def undo(self):
        """接続を削除"""
        if self.connection is not None:
            self.view.remove_edge(self.connection, self.source, self.target)


class MoveNodeCommand(QUndoCommand):
    """
    ノード移動のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードの移動操作のアンドゥ・リドゥ対応
    - ノードの位置変更の記録と復元
    - 移動前後の位置の管理
    
    主要なメソッド：
    - redo(): ノードの移動実行
    - undo(): ノードの移動取り消し
    """
    
    def __init__(self, node: 'NodeItem', old_pos: QPointF, new_pos: QPointF):
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
    """複数ノード移動コマンド"""
    
    def __init__(self, nodes: list['NodeItem'], old_positions: list[QPointF], new_positions: list[QPointF]):
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
    """
    関連ノードと一緒に移動するアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードとその関連ノード（子ノードなど）の一括移動
    - 複数ノードの移動操作のアンドゥ・リドゥ対応
    - ノード間の関係性を保った移動
    
    主要なメソッド：
    - redo(): 関連ノードの一括移動実行
    - undo(): 関連ノードの一括移動取り消し
    """
    
    def __init__(self, view: 'MindMapView', node: 'NodeItem', old_pos: QPointF, new_pos: QPointF):
        super().__init__("ノード移動（関連調整）")
        self.view = view
        self.node = node
        self.old_pos = QPointF(old_pos)
        self.new_pos = QPointF(new_pos)
        self.related_moves: list[tuple['NodeItem', QPointF, QPointF]] = []
    
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
    
    def _find_related_parent_nodes(self, moved_node: 'NodeItem') -> list['NodeItem']:
        """移動したノードに関連する親ノードを特定"""
        related_nodes = []
        all_nodes = [item for item in self.view.scene.items() if isinstance(item, 'NodeItem')]
        
        # 同じ階層レベルの他の親ノードを特定
        moved_level = self.view._calculate_node_level(moved_node, all_nodes)
        
        for node in all_nodes:
            if node != moved_node:
                node_level = self.view._calculate_node_level(node, all_nodes)
                if node_level == moved_level:
                    # 右側にあるノードを関連ノードとして追加
                    if node.pos().x() > moved_node.pos().x():
                        related_nodes.append(node)
        
        return related_nodes


class RenameNodeCommand(QUndoCommand):
    """ノードリネームコマンド"""
    
    def __init__(self, node: 'NodeItem', old_text: str, new_text: str):
        super().__init__("ノードリネーム")
        self.node = node
        self.old_text = old_text
        self.new_text = new_text
    
    def redo(self):
        self.node.text_item.setPlainText(self.new_text)
        self.node._update_text_position()
    
    def undo(self):
        self.node.text_item.setPlainText(self.old_text)
        self.node._update_text_position()


class DeleteNodeCommand(QUndoCommand):
    """
    ノード削除のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードの削除操作のアンドゥ・リドゥ対応
    - ノードとその接続線の削除
    - 削除されたノードの復元
    
    主要なメソッド：
    - redo(): ノードの削除実行
    - undo(): ノードの削除取り消し
    """
    
    def __init__(self, view: 'MindMapView', node: 'NodeItem'):
        super().__init__("ノード削除")
        self.view = view
        self.node = node
        self.node_text = node.text_item.toPlainText()
        self.node_pos = node.pos()
        self.connected_edges: list[tuple['CrankConnection', 'NodeItem', 'NodeItem']] = []
    
    def redo(self):
        # 接続されているエッジを記録して削除
        for connection, other_node in self.node._edges:
            self.connected_edges.append((connection, self.node, other_node))
            self.view.remove_edge(connection, self.node, other_node)
        
        # ノードを削除
        self.view.scene.removeItem(self.node)
    
    def undo(self):
        # ノードを復元
        self.node = self.view.add_node(self.node_text, self.node_pos)
        
        # 接続を復元
        for connection, source, target in self.connected_edges:
            if source == self.node:
                source.attach_edge(connection, target)
            else:
                target.attach_edge(connection, source)
        self.connected_edges.clear()

