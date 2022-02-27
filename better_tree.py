from json import tool
from uuid import uuid1
import ipywidgets as ipyw
from ipyevents import Event
from traitlets import Unicode, Int, link, observe


CSS = ipyw.HTML("""
<style>
.better-tree-btn {
    background: transparent;
    text-align: left;
}
.better-tree-small {
    text-align: center;
    background: transparent;
    padding:0;
	width: 15px;
}
.better-tree-selected {
    background: lightgrey;
    text-align: left;
}
</style>
""")


class Tree:
    def __init__(self):
        self.root = Node({'id':'root', 'label':'root'})
        self.root.level=0
        self.registry = {
            'root':self.root
        }

    def _disown(self, node):
        if node.parent is not None:
            old_parent = self.registry[node.parent]
            old_parent.children.remove(node.id)
        node.parent = None
    
    def _set_parent(self, node, parent, position=None):
        if position is None:
            parent.children.append(node.id)
        else:
            parent.children.insert(position, node.id)
        node.parent = parent.id

    def _validate(self):
        for id, node in self.registry.items():
            for c in node.children:
                assert self.registry[c].parent == id
        for id, node in self.registry.items():
            if id != 'root':
                assert id in self.registry[node.parent].children
                
    def get_depth(self, node):
        if isinstance(node, str):
            node = self.registry[node]
        return node.parent.level + 1
    
    def compute_depth(self, node_id='root', level=0):
        node = self.registry[node_id]
        node.level = level
        for c in node.children:
            self.compute_depth(c,level+1)
    
    def add_node(self, node):
        """
        add {node.id: node} to the registry
        set parent to 'root' if it is None
        """
        self.registry[node.id] = node
        if node.parent is None:
            self.move(node.id)  # append to children of 'root'
        self._validate()
        
    def add_multiple(self, nodes):
        for node in nodes:
            self.registry[node.id] = node
        for node in nodes:
            if node.parent is None:
                self._set_parent(node, self.root)  # append to children of 'root'
        self.compute_depth()
        self._validate()
    
    def move(self, node, parent='root', position=None):
        """
        Remove node from current parent's children (if applicable)
        Add node to new parent's children in the correct position
        Set the node's parent attribute to the new parent's id
        """
        if isinstance(node, str):
            node = self.registry[node]
        if isinstance(parent, str):
            parent = self.registry[parent]
        self._disown(node)
        self._set_parent(node, parent, position)
        self.compute_depth()
        self._validate()
    
    def remove(self, node, recursive=True, _first=True):
        node = node if isinstance(node, Node) else self.registry[node]
        if recursive:  # remove children from registry
            for c in node.children:
                self.remove(c, recursive,False)
        else:  # move children up
            for c in node.children:
                self.move(c, node.parent)
        
        # remove from registry
        self.registry.pop(node.id)
        
        # remove from parent's children
        self._disown(node)
        self.compute_depth()
        self._validate()
        
    def depth_first_search(self, id='root'):
        for c in self.registry[id].children:
            yield self.registry[c]
            yield from self.depth_first_search(c)

    def __repr__(self, id='root', level=0):
        collector = f"{' '*level}{self.registry[id]}\n"
        for c in self.registry[id].children:
            collector += self.__repr__(c, level+1)
        return collector
        

class Node:
    def __init__(self, data):
        self.data = data if data else {}
        self.id = self.data.get("id", str(uuid1()))
        self.parent = self.data.get("parent", None)
        self.children = self.data.get("children", [])
    
    def __repr__(self):
        return self.data["label"]


class TreeWidget(ipyw.VBox):
    def __init__(
        self,
        tree,
        height:int = 25,
    ):
        super().__init__()
        d = Event(
            source=self, 
            watched_events=["wheel"]  #, "mousemove", "mouseleave"]
        )
        d.on_dom_event(self.event_handler)

        self.tree = tree
        self.rows = [
            NodeWidget(
                self._open_callback,
                self._select_callback,
            ) for i in range(height)
        ]
        self.height = height
        self.cursor = 0
        self.selected = 'root'
        self._collapse_all()
        self.refresh()

    def _collapse_all(self):
        for id, node in self.tree.registry.items():
            node.opened = False
            node.selected = False
        self.tree.root.opened = True
    
    def _compute_visible(self, id='root'):
        collector = []
        node = self.tree.registry[id]
        collector.append(node)
        if node.opened:
            for c in node.children:
                collector += self._compute_visible(c)
        return collector
    
    def _compute_inview(self):
        self._visible = self._compute_visible()
        return self._visible[self.cursor : self.cursor+self.height]

    def _open_callback(self, id, value):
        self.tree.registry[id].opened = value
        self.refresh()
        
    def _select_callback(self, id):
        self.tree.registry[self.selected].selected = False
        self.tree.registry[id].selected = True
        self.selected = id
        self.refresh()
        
    def _add_node_callback(self, **kwargs):
        self.tree.add_node(**kwargs)
        self.refresh()

    def scroll(self, val):
        self.cursor += val
        self.cursor = max(self.cursor, 0)
        self.cursor = min(self.cursor, len(self._visible) - self.height)
        self.refresh()

    def event_handler(self, event):
        # print(event)
        if "deltaY" in event:
            to_scroll = 1 if event["deltaY"] > 0 else -1
            self.scroll(to_scroll)

    def refresh(self):
        inview = self._compute_inview()
        for i,node in enumerate(inview):
            self.rows[i].load(node)
        self.children = self.rows[:len(inview)] + [CSS]
            
    
class NodeWidget(ipyw.HBox):
    icon = Unicode("")
    tooltip = Unicode("")
    label = Unicode("")
    indent = Int(0)
    def __init__(
        self,
        _open_callback,
        _select_callback,
    ):
        super().__init__()

        # Callbacks
        self._open_callback = _open_callback
        self._select_callback = _select_callback


        # State Variables
        self.opened = False

        # Widgets
        self.button = ipyw.Button()
        self.expand_btn = ipyw.Button()
        self.html = ipyw.HTML()
        self.indent_box = ipyw.HTML()

        self.children = [
            self.indent_box,
            self.expand_btn,
            self.button,
            self.html
        ]


        # Style
        self.expand_btn.add_class("better-tree-small")
        self.button.add_class("better-tree-btn")

        # Events
            # Button Clicks
        self.button.on_click(self.select)
        self.expand_btn.on_click(self.expand)

            # Traitlets
        link((self, "icon"), (self.button, "icon"))
        link((self, "tooltip"), (self.button, "tooltip"))
        link((self, "label"), (self.html, "value"))
        
    def expand(self, _=None):
        self.opened = not self.opened
        self.expand_btn.icon = 'angle-down' if self.opened else 'angle-right'
        self._open_callback(self.id, self.opened)
        
    def select(self, _=None):
        self.button.add_class("better-tree-selected")
        self._select_callback(self.id)
        
    def load(self, node):
        self.button.icon = node.data.get("icon","align-justify")
        self.button.description = node.data.get("label","")
        self.indent_box.value = "&nbsp"*node.level*3
        self.opened = node.opened
        if node.children:
            if node.opened:
                self.expand_btn.icon = 'chevron-down' 
            else:
                self.expand_btn.icon = 'chevron-right'
        else:
            self.expand_btn.icon = 'none'

        if node.selected:
            self.button.add_class("better-tree-selected")
        else:
            self.button.remove_class("better-tree-selected")
        
        self.id = node.id