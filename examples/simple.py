from hyena import Template, Dummy

# silent type checkers
system = node = Dummy()


class Transition(Template):
    def action(self):
        idx = node.inputs[0].node
        if node.current == system.nodes[idx].current:
            return 0
        else:
            return 1
