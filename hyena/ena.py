from . import *


@dataclass
class Transition(Struct):
    target: Annotated[int,
                      F.PRIME()
                      | F.INDEX("Node.locations")]
    action: Annotated[Callable[[], None],
                      F.PRIME()]


@dataclass
class Location(Struct):
    transitions: Annotated[list[Transition],
                           F.PRIME()]


@dataclass
class Input(Struct):
    node: Annotated[int,
                    F.PRIME()
                    | F.INDEX("System.nodes")]


@dataclass
class Node(Struct):
    inputs: list[Input]
    locations: Annotated[list[Location],
                         F.PRIME()]
    current: Annotated[int,
                       F.PRIME()
                       | F.MUTABLE()
                       | F.INDEX(".locations")]


@dataclass
class System(Struct):
    nodes: Annotated[list[Node],
                     F.PRIME()]

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
                try:
                    act = trans.action()
                    self[path[:2]].current = trans.target
                    yield self.state, path, act
                except Abort:
                    pass
                except Jump as jmp:
                    for nid, loc in jmp.jumps.items():
                        node = self.nodes[nid]
                        if 0 <= loc < len(node.locations):
                            node.current = loc
                        else:
                            raise ValueError(f"invalid jump to {loc}"
                                             f" in node {nid}")
                    yield self.state, path, jmp.cost
            finally:
                self.state = old
