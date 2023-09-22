from hyena import template

@template
class Transition:
    guard = "True"
    update = ""
    def cost():
        if sameloc():
            return 0
        else:
            return 1
    def sameloc():
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current
