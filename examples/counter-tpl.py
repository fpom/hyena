from hyena import template

@template
class Transition:
    guard = "True"
    cost = "node.count * sameloc()"
    update = "node.count += 1"
    def sameloc():
        in0de = node.inputs[0].node
        if node.current == system.nodes[in0de].current:
            return 0
        else:
            return 1

@template
class Node:
    current = 0
    count = 0
