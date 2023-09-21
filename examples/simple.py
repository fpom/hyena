from hyena import template

@template
class Transition:
    guard = "True"
    cost = "0 if node.current == system.nodes[node.inputs[0].node].current else 1"
    update = ""
