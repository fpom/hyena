from . import *


@dataclass
class Transition(Struct):
    target: Prime[Const[Index["Node.locations"]]]
    action: Prime[Const[Action]]


@dataclass
class Location(Struct):
    transitions: Prime[Const[Array[Transition]]]


@dataclass
class Input(Struct):
    node: Prime[Const[Index["System.nodes"]]]


@dataclass
class Node(Struct):
    inputs: Const[Array[Input]]
    locations: Prime[Const[Array[Location]]]
    current: Prime[Index[".locations"]]


@dataclass
class System(Struct):
    nodes: Prime[Const[Array[Node]]]

    def __post_init__(self):
        super().__post_init__()
        self._bind_methods()

    def succ(self, state=None):
        old = self.state
        if state is None:
            state = old
        else:
            self.state = state
        todo = [("nodes", n, "locations", node.current, "transitions", t)
                for n, node in enumerate(self.nodes)
                for t in range(len(node.locations[node.current].transitions))]
        for path in todo:
            trans = self[path]
            try:
                self.state = state
                act = trans.action()
                if act is not None:
                    self[path[:2]].current = trans.target
                    yield self.state, path, act
            finally:
                self.state = old
