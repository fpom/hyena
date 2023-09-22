from . import *

@dataclass
class Transition(Struct):
    target: Prime[Const[Index["Node.locations"]]]
    guard: Prime[Const[Expr[bool]]]
    cost: Prime[Const[Expr[int]]]
    update: Prime[Const[Stmt]]
    def succ(self, state, env, path):
        env = env|self.env
        if state.eval(self.guard, env):
            cost = state.eval(self.cost, env)
            yield state.exec(self.update, env), path, cost
    def __post_init__(self):
        if self.update:
            if func_def.match(self.update):
                self.update += "\n    node.current = transition.target"
            else:
                self.update += "; node.current = transition.target"
        else:
            self.update = "node.current = transition.target"


@dataclass
class Location(Struct):
    outputs: Prime[Const[Array[Transition]]]
    def succ(self, state, env, path):
        for num, trans in enumerate(self.outputs):
            yield from trans.succ(state, env|self.env, path + ("outputs", num))

@dataclass
class Input(Struct):
    node: Prime[Const[Index["System.nodes"]]]

@dataclass
class Node(Struct):
    inputs: Const[Array[Input]]
    locations: Prime[Const[Array[Location]]]
    current: Prime[Index[".locations"]]
    def succ(self, state, env, path):
        loc = self.locations[self.current]
        yield from loc.succ(state, env|self.env, path + ("locations", self.current))

@dataclass
class System(Struct):
    nodes: Prime[Const[Array[Node]]]
    def succ(self, state=None):
        if state is None:
            state = self.state
        for num, node in enumerate(self.nodes):
            yield from node.succ(state, self.env, ("nodes", num))
