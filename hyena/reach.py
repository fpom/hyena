import collections
import json

from .simul import Event, Trans


class AssertFailed(Exception):
    def __init__(self, prop, state, err=None):
        super().__init__(f"assert {prop} failed on state {state}")
        self.prop = prop
        self.state = state
        self.err = err


class Explorer:
    def __init__(self, system, depth=False, limit=None, props=[]):
        self.system = system
        self.init = self.system.state
        self.succ = {}
        self.todo = collections.deque([self.init])
        self.depth = depth
        self.limit = limit
        self.props = dict(self.compile(props))

    def __iter__(self):
        while self.todo:
            if self.depth:
                state = self.system.state = self.todo.pop()
            else:
                state = self.system.state = self.todo.popleft()
            for src, code in self.props.items():
                try:
                    check = eval(code, {"system": self.system})
                except Exception as err:
                    raise AssertFailed(src, state, err)
                if not check:
                    raise AssertFailed(src, state)
            succ = tuple(self.system.succ(state))
            self.succ[state] = succ
            keep = []
            for s, *_ in succ:
                if (s not in self.succ
                        and (self.limit is None
                             or len(self) < self.limit)):
                    self.todo.append(s)
                    keep.append(s)
                    self.succ[s] = None
            yield state, keep

    def __len__(self):
        return len(self.succ)

    def compile(self, props):
        for num, prop in enumerate(props):
            try:
                yield prop, compile(prop, f"<assert #{num}>", "eval")
            except Exception as err:
                raise AssertFailed(prop, None, err)

    def save(self, out):
        json.dump([
            {
                "state": state,
                "succs": [
                    {
                        "state": s,
                        "trans": t,
                        "action": a
                    } for s, t, a in succ]
            } for state, succ in self.succ.items()
        ], out, indent=2)

    def trace(self, state):
        init = [Event(self.init, None, 0)]
        if state == self.init:
            return init
        old_paths = [init]
        seen = {self.init}
        while len(seen) < len(self.succ):
            new_paths = []
            for old in old_paths:
                for s, t, c in self.succ[old[-1].state]:
                    new = old + [Event(s, Trans(t), c)]
                    if s == state:
                        return new
                    elif s not in seen:
                        seen.add(s)
                        new_paths.append(new)
            old_paths = new_paths
        return []
