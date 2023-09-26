from hyena import template


@template
class Transition:
    def guard():
        return True

    def cost():
        idx = node.inputs[0].node
        if node.current == system.nodes[idx].current:
            return 0
        else:
            return 1

    def update():
        pass
