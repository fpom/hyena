from hyena import Template, Dummy

# to silent typecheckers
system = node = Dummy()


class Transition(Template):
    guard = "True"

    def cost(self):
        if self.sameloc():
            return 0
        else:
            return node.count

    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current

    def update(self):
        node.count += 1


class Node(Template):
    current = 0
    count = 0
