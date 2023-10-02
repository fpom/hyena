import collections
import importlib
import sys
import json

from colorama import Fore as F, Style as S
from .simul import Event, Trans, tree


class AssertFailed(Exception):
    def __init__(self, prop, state, exc=None):
        super().__init__(f"assert {prop} failed on state {state}")
        self.prop = prop
        self.state = state
        self.exc = exc


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
            for s, *_ in succ:
                if (s not in self.succ
                        and (self.limit is None
                             or len(self) < self.limit)):
                    self.todo.append(s)
                    self.succ[s] = None
            yield state, succ

    def __len__(self):
        return len(self.succ)

    def progress(self, newline=False):
        sys.stdout.write(f"\r{F.YELLOW}...{F.RESET} {len(self)} state"
                         f"{'s' if len(self) > 1 else ''}"
                         f" {S.DIM}+ {len(self.todo)} to explore"
                         f"{S.RESET_ALL}")
        if newline:
            sys.stdout.write("\n")
        sys.stdout.flush()

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
                        "cost": c
                    } for s, t, c in succ]
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--class", dest="cls", type=str, metavar="CLASS",
                        default="hyena.ena.System",
                        help=("System class to be loaded"
                              " (default: `hyena.ena.System`)"))
    parser.add_argument("-j", "--json", type=str, metavar="PATH",
                        help="JSON file to be loaded")
    parser.add_argument("-p", "--python", type=str, metavar="PATH",
                        help="Python template to be loaded")
    parser.add_argument("-v", "--verbose", default=False, action="store_true",
                        help="print states as they are explored")
    parser.add_argument("-a", "--assert", default=[], metavar="EXPR",
                        action="append", dest="props",
                        help="property to check on state")
    parser.add_argument("-t", "--trace", default=False, action="store_true",
                        help="print a trace to a state found violating assert")
    parser.add_argument("-s", "--save", default=None, metavar="PATH",
                        type=argparse.FileType("w"),
                        help="save state-space as JSON to PATH")
    parser.add_argument("-l", "--limit", default=None, type=int, metavar="NUM",
                        help="limit exploration to NUM states")
    parser.add_argument("-d", "--depth", default=False, action="store_true",
                        help=("explore depth-first instead of"
                              " the default breadth-first"))
    args = parser.parse_args()
    modname, classname = args.cls.rsplit(".", 1)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        parser.exit(2, (f"could not import '{modname}.{classname}'"
                        f" ({err.__class__.__name__}: {err})\n"))
    system = cls.from_json(args.json, args.python)
    explorer = None
    try:
        explorer = Explorer(system,
                            depth=args.depth,
                            limit=args.limit,
                            props=args.props)
        for state, succs in explorer:
            if args.verbose:
                print(state, f"{S.DIM}=> +{len(succs)}{S.RESET_ALL}")
            explorer.progress(args.verbose)
    except KeyboardInterrupt:
        pass
    except AssertFailed as err:
        lines = []
        if not args.verbose and explorer is not None and len(explorer):
            print()
        if err.state is None:
            lines = [f"{F.RED}invalid assert:{F.RESET} {err.prop}"]
        else:
            lines = [f"{F.RED}assert failed:{F.RESET} {err.prop}"]
            lines.append(f"{F.RED}on state:{F.RESET} {err.state}")
        if err.exc is not None:
            lines.append(f"{F.RED}raised {err.exc.__class__.__name__}:"
                         f"{F.RESET} {err.exc}")
        if args.trace and explorer is not None and err.state is not None:
            print(f"{F.RED}### trace ###{F.RESET}")
            cost = 0
            for n, e in enumerate(explorer.trace(err.state)):
                if e.trans is not None:
                    cost += e.cost
                    print(f"{F.RED}>>>{F.RESET} system.{e.trans}"
                          f" {S.DIM}{F.RED}(+${e.cost}"
                          f" => ${cost}){S.RESET_ALL}")
                print(tree(f"{F.BLUE}#{n}:{F.RESET}", e.state))
        parser.exit(3, "\n".join(lines) + "\n")
    if not args.verbose:
        print()
    if args.save is not None and explorer is not None:
        explorer.save(args.save)
