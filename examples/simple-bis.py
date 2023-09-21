from hyena import template

@template
class Transition:
    guard = "True"
    cost = "sameloc()"
    update = ""
    def sameloc():
        in0de = node.inputs[0].node
        if node.current == system.nodes[in0de].current:
            return 0
        else:
            return 1
