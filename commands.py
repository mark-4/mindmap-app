"""
Undo/Redoコマンド
"""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand
from node import NodeItem


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
        
        # 新しく作成されたノードを選択
        if self.node is not None:
            # 他のノードの選択を解除
            for item in self.view.scene.selectedItems():
                item.setSelected(False)
            # 新しいノードを選択
            self.node.setSelected(True)
    
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
    - 接続線の自動更新
    
    主要なメソッド：
    - redo(): ノードの移動実行
    - undo(): ノードの移動取り消し
    """
    
    def __init__(self, view: 'MindMapView', node: 'NodeItem', old_pos: QPointF, new_pos: QPointF):
        super().__init__("ノード移動")
        self.view = view
        self.node = node
        self.old_pos = QPointF(old_pos)
        self.new_pos = QPointF(new_pos)
    
    def redo(self):
        self.node.setPos(self.new_pos)
        # 接続線を更新
        for connection in self.view.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source == self.node or connection.target == self.node)):
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        self.view.scene.update()
    
    def undo(self):
        self.node.setPos(self.old_pos)
        # 接続線を更新
        for connection in self.view.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source == self.node or connection.target == self.node)):
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
        self.view.scene.update()


class MoveMultipleNodesCommand(QUndoCommand):
    """
    複数ノード移動のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - 複数ノードの一括移動操作のアンドゥ・リドゥ対応
    - 複数ノードの位置変更の記録と復元
    - 接続線の自動更新
    
    主要なメソッド：
    - redo(): 複数ノードの移動実行
    - undo(): 複数ノードの移動取り消し
    """
    
    def __init__(self, view: 'MindMapView', nodes: list['NodeItem'], old_positions: list[QPointF], new_positions: list[QPointF]):
        super().__init__("複数ノード移動")
        self.view = view
        self.nodes = nodes
        self.old_positions = [QPointF(pos) for pos in old_positions]
        self.new_positions = [QPointF(pos) for pos in new_positions]
    
    def redo(self):
        """複数ノードを新しい位置に移動"""
        for node, new_pos in zip(self.nodes, self.new_positions):
            node.setPos(new_pos)
        
        # 移動したノードに関連する接続線を更新
        self._update_connections()
        self.view.scene.update()
    
    def undo(self):
        """複数ノードを元の位置に戻す"""
        for node, old_pos in zip(self.nodes, self.old_positions):
            node.setPos(old_pos)
        
        # 移動したノードに関連する接続線を更新
        self._update_connections()
        self.view.scene.update()
    
    def _update_connections(self):
        """移動したノードに関連する接続線を更新"""
        for connection in self.view.connections:
            if (hasattr(connection, 'source') and hasattr(connection, 'target') and
                (connection.source in self.nodes or connection.target in self.nodes)):
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()


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
    """
    ノードリネームのアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードのテキスト変更のアンドゥ・リドゥ対応
    - テキスト変更前後の状態管理
    - テキスト位置の自動調整
    
    主要なメソッド：
    - redo(): ノードのテキスト変更実行
    - undo(): ノードのテキスト変更取り消し
    """
    
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


class SubtreeMoveCommand(QUndoCommand):
    """
    サブツリー移動のアンドゥ・リドゥコマンド
    
    このクラスは以下の機能を提供します：
    - ノードとその子孫ノードの一括移動
    - サブツリー全体の移動操作のアンドゥ・リドゥ対応
    - 接続線の状態保存と復元
    
    主要なメソッド：
    - redo(): サブツリーの移動実行
    - undo(): サブツリーの移動取り消し
    """
    
    def __init__(self, view: 'MindMapView', root_node: 'NodeItem', old_positions: dict, new_positions: dict, old_connections: dict):
        super().__init__("サブツリー移動")
        self.view = view
        self.root_node = root_node
        self.old_positions = old_positions.copy()
        self.new_positions = new_positions.copy()
        self.old_connections = old_connections.copy()
    
    def redo(self):
        # ノード位置を復元
        for node, new_pos in self.new_positions.items():
            node.setPos(new_pos)
        
        # 接続線を更新
        for connection in self.view.connections:
            if hasattr(connection, 'update_connection'):
                connection.update_connection()
        self.view.scene.update()
    
    def undo(self):
        # ノード位置を元に戻す
        for node, old_pos in self.old_positions.items():
            node.setPos(old_pos)
        
        # 接続線を元の状態に戻す
        for connection_id, connection_data in self.old_connections.items():
            for connection in self.view.connections:
                if id(connection) == connection_id:
                    if connection.horizontal_line1 and connection_data.get('horizontal_line1_line'):
                        connection.horizontal_line1.setLine(connection_data['horizontal_line1_line'])
                    if connection.vertical_line and connection_data.get('vertical_line_line'):
                        connection.vertical_line.setLine(connection_data['vertical_line_line'])
                    if connection.horizontal_line2 and connection_data.get('horizontal_line2_line'):
                        connection.horizontal_line2.setLine(connection_data['horizontal_line2_line'])
                    break
        
        self.view.scene.update()


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


class ReorderNodeCommand(QUndoCommand):
    """ノードの順番変更コマンド"""
    
    def __init__(self, view, parent_node, dragged_node, old_index, new_index):
        super().__init__()
        self.view = view
        self.parent_node = parent_node
        self.dragged_node = dragged_node
        self.old_index = old_index
        self.new_index = new_index
        self.old_positions = {}
        self.new_positions = {}
        
    def redo(self):
        """順番変更を実行"""
        try:
            # 子ノードの現在位置を保存
            child_nodes = []
            for conn in self.view.connections:
                if (hasattr(conn, 'source') and hasattr(conn, 'target') and
                    conn.source == self.parent_node):
                    child_nodes.append(conn.target)
            
            # 古い位置を保存
            for child in child_nodes:
                self.old_positions[child] = child.pos()
            
            # 順番を変更
            child_nodes.remove(self.dragged_node)
            child_nodes.insert(self.new_index, self.dragged_node)
            
            # 新しい位置を計算・適用
            self.view._reposition_child_nodes(self.parent_node, child_nodes)
            
            # 新しい位置を保存
            for child in child_nodes:
                self.new_positions[child] = child.pos()
                
        except Exception as e:
            print(f"ReorderNodeCommand redo エラー: {e}")
    
    def undo(self):
        """順番変更を元に戻す"""
        try:
            # 古い位置に戻す
            for child, old_pos in self.old_positions.items():
                child.setPos(old_pos)
            
            # 接続線を更新
            for connection in self.view.connections:
                if hasattr(connection, 'update_connection'):
                    connection.update_connection()
                    
        except Exception as e:
            print(f"ReorderNodeCommand undo エラー: {e}")


