from hyena import Template, Dummy, Jump

# to silent typecheckers
system = node = Dummy()


class Transition(Template):
    def action(self):
        node.count += 1
        if node.count == 3:
            node.count = 0
            raise Jump(0, {0: 0, 1: 0})
        elif self.sameloc():
            return 0
        else:
            return node.count

    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current


class Node(Template):
    current = 0
    count = 0
