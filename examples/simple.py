from hyena import Template, Dummy

# silent type checkers
system = node = Dummy()


class Transition(Template):
    def guard(self):
        return True

    def cost(self):
        idx = node.inputs[0].node
        if node.current == system.nodes[idx].current:
            return 0
        else:
            return 1

    def update(self):
        pass
