from hyena import template

@template
class Transition:
    guard = "True"
    def cost():
        if sameloc():
            return 0
        else:
            return node.count
    def sameloc():
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current
    def update():
        node.count += 1

@template
class Node:
    current = 0
    count = 0
