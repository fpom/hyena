from hyena import Template, ena

# silent type checkers
system = ena.System.dummy()
node = ena.Node.dummy()


class Transition(Template):
    def action(self):
        idx = node.inputs[0].node
        if node.current == system.nodes[idx].current:
            return 0
        else:
            return 1
