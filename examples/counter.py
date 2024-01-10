from hyena import ena, Annotated, F
from hyena.ena import *


@dataclass
class Node(ena.Node):
    count: Annotated[int, F.MUTABLE()]


@dataclass
class System(ena.System):
    pass
