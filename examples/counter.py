from hyena import Field, ena
from hyena.ena import *

@dataclass
class Node(ena.Node):
    count: Field[int]

@dataclass
class System(ena.System):
    pass
