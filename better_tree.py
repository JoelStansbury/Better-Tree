# Author: Joel Stansbury
# Email: stansbury.joel@gmail.com 

from pathlib import Path
import time
from uuid import uuid1
import ipywidgets as ipyw
from ipyevents import Event
from traitlets import Unicode, Int, link, observe
from typing import Union, List


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


class Node:
    def __init__(self, data):
        self.data = data if data else {}
        self.id = self.data.get("id", str(uuid1()))
        self.parent = self.data.get("parent", None)
        self.children = self.data.get("children", [])
        self.opened = False
        self.selected = False
    
    def __repr__(self):
        return self.data["label"]
    
    def to_dict(self):
        self.data["id"] = self.id
        self.data["parent"] = self.parent
        self.data["children"] = self.children
        return self.data


class Tree:
    def __init__(self, nodes=None):
        """
        nodes <list[dict]> (None): This must be a flat (not nested) list
            of dictionaries as returned by `Tree.to_dict()`. The nodes
            are added via `Tree.add_multiple(nodes)`
        """
        self.root = Node({'id':'root', 'label':'root'})
        self.root.level=0
        self.registry = {
            'root':self.root
        }
        self.listeners = []
        if nodes:
            self.add_multiple(nodes)

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
                assert c in self.registry, "child does not exist"
                assert self.registry[c].parent == id, \
                    f"child {self.registry[c]} has a different parent: {self.parent_of(c)}.\n" + \
                    f"Should be: {self.registry[id]}"

        for id, node in self.registry.items():
            if id != 'root':
                assert id in self.registry[node.parent].children
 
    def _compute_depth(self, node_id='root', level=0):
        # TODO: Collect some statistics about this. It may actually
        # be more efficient to recompute the depth for the 20
        # visible nodes everytime, versus computing all depths
        # on an alteration
        node = self.registry[node_id]
        node.level = level
        for c in node.children:
            self._compute_depth(c,level+1)

    def _notify_widgets(self):
        for f in self.listeners:
            f()

    def _housekeeping(self):
        self._validate()
        self._compute_depth()
        self._notify_widgets()

    def _handle_type(self, node:Union[str, Node, dict], allow_creation=False):
        if isinstance(node, str):
            return self.registry[node] 
        if isinstance(node, dict):
            if node["id"] in self.registry:
                return self.registry[node["id"]]
            if allow_creation:
                return Node(node)
        return node

    def parent_of(self, node):
        return self._handle_type(self._handle_type(node).parent)

    def add_node(self, node:Union[Node,dict]):
        """
        add {node.id: node} to the registry
        set parent to 'root' if it is None
        """
        node = self._handle_type(node, allow_creation=True)
        assert node.id not in self.registry, "that id is already in use"
        self.registry[node.id] = node
        if node.parent is None:
            self.move(node.id)  # append to children of 'root'
        self._housekeeping()
    
    def get_depth(self, node):
        node = self._handle_type(node)
        return node.parent.level + 1
    
    def add_multiple(
        self,
        node_list: List[Union[Node,dict]],
        parent:Union[str, Node] = 'root'
    ):
        """
        Assumes all parent and children relationships are compatible
        """
        parent = self._handle_type(parent)
        node_list = [
            self._handle_type(node, allow_creation=True)
            for node in node_list
        ]
        for node in node_list:
            self.registry[node.id] = node
        for node in node_list:
            if node.parent is None:
                self._set_parent(node, parent)
        self._housekeeping()
    
    def move(
        self,
        node:Union[str, Node],
        parent:Union[str, Node]='root',
        position: int=None
    ):
        """
        Remove node from current parent's children (if applicable)
        Add node to new parent's children in the correct position
        Set the node's parent attribute to the new parent's id
        """
        node = self._handle_type(node)
        parent = self._handle_type(parent)
        self._disown(node)
        self._set_parent(node, parent, position)
        self._housekeeping()

    def _insert_nested_dict(
        self,
        node_data:dict,
        parent_id:str='root',
        children_key:str='children',
    ):
        node_data['parent'] = parent_id
        if children_key in node_data:
            children_list = node_data.pop(children_key)
        else:
            children_list = []
        node_data["children"]=[]
        node = Node(node_data)
        self.registry[parent_id].children.append(node.id)
        self.registry[node.id] = node
        for child in children_list:
            self._insert_nested_dict(
                child,parent_id=node.id,children_key=children_key,
            )
 
    def insert_nested_dicts(
        self,
        node_data_list:List[dict],
        children_key:str='children',
        parent_id:str=None
    ):
        if parent_id is None:
            parent_id = self.root.id
        for node_data in node_data_list:
            self._insert_nested_dict(
                node_data=node_data,
                children_key=children_key,
                parent_id=parent_id
            )
        self._housekeeping()
    
    def remove(
        self, 
        node:Union[str, Node],
        recursive:bool=True
    ):
        node = self._handle_type(node)
        if recursive:  # remove children from registry
            for c in list(self.dfs(node.id)):
                self.registry.pop(c.id)
        else:  # move children up
            for c in node.children:
                self.move(c, node.parent)
        
        # remove from registry
        self.registry.pop(node.id)
        
        # remove from parent's children
        self._disown(node)
        self._housekeeping()

    def bfs(self, node_ids:Union[str, List[str]]='root'):
        if isinstance(node_ids, str):
            node_ids = [node_ids]
        next_ids = sum(
            [self.registry[node_id].children for node_id in node_ids],
            []
        )
        if next_ids:
            for c in next_ids:
                yield self.registry[c]
            yield from self.bfs(next_ids)
    
    def dfs(self, node_id:str='root'):
        for c in self.registry[node_id].children:
            yield self.registry[c]
            yield from self.dfs(c)

    def to_list(self, node_id:str='root'):
        result = []
        for node in self.dfs(node_id):
            d = node.to_dict()
            if d["parent"] == node_id:
                d["parent"] = None
            result.append(d)
        return result

    def rglob(self, root, pattern):
        """
        Constructs a tree from an rglob search
        """
        root = Path(root)
        skip = len(root.parts)
        self.registry = {'root':self.root}
        self.root.data['label'] = str(root)
        self.root.data['icon'] = 'folder'

        icons = {
            'pdf':'file-pdf',
            'xlsx':'file-excel',
            'xlsm':'file-excel',
            'xls':'file-excel',
            'csv':'file-csv',
            'zip':'file-zipper',
            'gzip':'file-zipper',
            'tar':'file-zipper',
            '7z':'file-zipper',
            'png':'file-image',
            'jpeg':'file-image',
            'jpg':'file-image',
        }

        nodes = {'children':[]}
        for p in list(root.rglob(pattern)):
            cursor = nodes
            _id = root
            for part in p.parts[skip:]:
                _id = _id / part
                if not part in [x['label'] for x in cursor["children"]]:
                    icon = 'folder'
                    if len(part.split('.'))>1:
                        icon = 'file'
                        if part.split('.')[-1] in icons:
                            icon = icons[part.split('.')[-1]]
                    cursor['children'].append(
                        {
                            'id':str(_id),
                            'label':part,
                            'children':[],
                            'icon':icon
                        }
                    )
                cursor = [x for x in cursor["children"] if x['label'] == part][0]
        self.insert_nested_dicts(nodes["children"])

    def __repr__(self, node_id:str='root', level=0):
        collector = f"{' '*level}{self.registry[node_id]}\n"
        for c in self.registry[node_id].children:
            collector += self.__repr__(c, level+1)
        return collector


class TreeWidget(ipyw.VBox):
    selected_id = Unicode('root')
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
        self.tree.listeners.append(self.refresh)
        self.rows = [
            NodeWidget(
                self._open_callback,
                self._select_callback,
            ) for i in range(height)
        ]

        self.height = height
        self.cursor = 0
        self.selected_node = None

        self.scroll_speed = 1 # set and incrimented in self.scroll
        self.last_scroll_time = time.time()

        self._collapse_all()
        self.refresh()

    def _collapse_all(self):
        for id, node in self.tree.registry.items():
            node.opened = False
            node.selected = False
        self.tree.root.opened = True
    
    @observe("selected_id", type="change")
    def _update_selected_node(self, event):
        if event["new"]:
            self.selected_node = self.tree.registry[self.selected_id]
    
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
        self.tree.registry[self.selected_id].selected = False
        self.tree.registry[id].selected = True
        self.selected_id = id
        self.refresh()
        
    def _add_node_callback(self, **kwargs):
        self.tree.add_node(**kwargs)
        self.refresh()

    def scroll(self, val):

        self.cursor += val
        self.cursor = min(self.cursor, len(self._visible) - self.height)
        self.cursor = max(self.cursor, 0)
        self.refresh()

    def event_handler(self, event):
        # print(event)
        if "deltaY" in event:
            if time.time() - self.last_scroll_time < 0.1:
                self.scroll_speed += 2
            else:
                self.scroll_speed = 1
            self.last_scroll_time = time.time()

            to_scroll = self.scroll_speed if event["deltaY"] > 0 else -self.scroll_speed
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
