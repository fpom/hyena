from hyena import Template, Dummy

# silent type checkers
system = node = Dummy()


class Transition(Template):
    guard = "True"
    update = ""

    def cost(self):
        if self.sameloc():
            return 0
        else:
            return 1

    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current
