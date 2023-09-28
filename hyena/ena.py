from . import *

@dataclass
class Transition(Struct):
    target: Prime[Const[Index["Node.locations"]]]
    guard: Prime[Const[Expr[bool]]]
    cost: Prime[Const[Expr[int]]]
    update: Prime[Const[Stmt]]

    def succ(self, path):
        if self.guard():
            cost = self.cost()
            yield self, path, cost


@dataclass
class Location(Struct):
    transitions: Prime[Const[Array[Transition]]]

    def succ(self, path):
        for num, trans in enumerate(self.transitions):
            yield from trans.succ(path + ("transitions", num))


@dataclass
class Input(Struct):
    node: Prime[Const[Index["System.nodes"]]]


@dataclass
class Node(Struct):
    inputs: Const[Array[Input]]
    locations: Prime[Const[Array[Location]]]
    current: Prime[Index[".locations"]]

    def succ(self, path):
        loc = self.locations[self.current]
        yield from loc.succ(path + ("locations", self.current))


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
        for num, node in enumerate(self.nodes):
            for trans, path, cost in node.succ(("nodes", num)):
                trans.update()
                node.current = trans.target
                yield self.state, path, cost
                self.state = state
        self.state = old
