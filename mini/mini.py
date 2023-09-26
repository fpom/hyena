from hyena import template


@template
class Transition:
    # declare here all constants and functions that will be in transition.env
    # default guard for every transition is True
    guard = "True"
    # default cost for every transition is 0
    cost = 0
    # default update for every transition is empty
    update = ""

    def isUp(src):
        "test whether source node src is not down"
        # such a declaration is currently not allowed because its type is
        # neither bool nor int, but we could allow it as a macro, ie,
        # node cannot be redefined and will be syntactically substituted
        n = system.nodes[src]
        return n.locations[n.current].status != STATUS.down

    def isMalware(src):
        "test whether source not src is infected by a malware"
        n = system.nodes[src]
        return n.locations[n.current].status == STATUS.malware


@template
class Location:
    # declare here all constants and functions that will be in location.env
    # default fields values
    transitions = []


@template
class Node:
    # declare here all constants and functions that will be in node.env
    # default fields values
    current = 0
    inputs = []
    secrets = [False]
    locations = [
        Location(
            status="ok",
            transitions=[
                Transition(
                    target=1,
                    guard="location.status != STATUS.down and any(isUp(i.node) and isMalware(i.node) for i in node.inputs)",
                    cost=3,
                    update="system.stolen[0] = True"
                )
            ]
        ),
        Location(
            status="malware"
        )
    ]


@template
class System:
    # declare here all constants and functions that will be in system.env
    # default fields values
    nbSecrets = 1
    stolen = [False]
