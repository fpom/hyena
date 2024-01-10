from hyena import ena
from hyena.ena import *


@dataclass
class Node(ena.Node):
    count: int


@dataclass
class System(ena.System):
    pass
