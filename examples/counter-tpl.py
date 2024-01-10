from hyena import ena, Template

# to silent typecheckers
system = ena.System.dummy()
node = ena.Node.dummy()


class Transition(Template):
    def action(self):
        node.count += 1
        if self.sameloc():
            return 0
        else:
            return node.count

    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current


class Node(Template):
    current = 0
    count = 0
