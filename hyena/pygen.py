import subprocess
import inspect
import secrets
import io

from . import Field, Struct as BaseStruct, EnumType, State, array, func_def
from colorama import Style as S, Fore as F


def pygen_headers(out):
    out.write("import secrets, io, readline\n"
              "from enum import StrEnum\n"
              "from frozendict import frozendict\n"
              "from colorama import Style as S, Fore as F\n\n")
    out.write("##\n## auxiliary stuff\n##\n\n")
    out.write(inspect.getsource(array) + "\n")


def pygen_enum(cls, out):
    values = [str(v) for v in cls]
    out.write(f"{cls.__name__} = StrEnum('{cls.__name__}', {values!r})\n\n")


def pygen_class(cls, out):
    state = []
    for name, field in cls.__dataclass_fields__.items():
        ftype = Field(field.type, cls)
        if ftype.func:
            continue
        elif issubclass(ftype.base, BaseStruct):
            state.append(name)
        elif not ftype.const:
            state.append(name)
    out.write(f"class {cls.__name__}:\n"
              f"    __state__ = {tuple(state)}\n")
    out.write(f"    def __init__(self,"
              f"{', '.join(cls.__dataclass_fields__)}):\n"
              f"        self.__fields__ = {{}}\n")
    for name, field in cls.__dataclass_fields__.items():
        ftype = Field(field.type, cls)
        if ftype.func:
            out.write(f"        # '{name}' will be added later on\n")
        elif ftype.array:
            orval = " or []" if ftype.option or not ftype.prime else ""
            if ftype.const:
                out.write(f"        self.__fields__[{name!r}]"
                          f" = tuple({name}{orval})\n")
            else:
                out.write(f"        self.__fields__[{name!r}]"
                          f" = array({name}{orval})\n")
        else:
            out.write(f"        self.__fields__[{name!r}] = {name}\n")
    for name, field in cls.__dataclass_fields__.items():
        ftype = Field(field.type, cls)
        if ftype.func:
            continue
        out.write(f"    @property\n"
                  f"    def {name}(self):\n"
                  f"        return self.__fields__[{name!r}]\n")
        if ftype.const or ftype.array:
            continue
        out.write(f"    @{name}.setter\n"
                  f"    def {name}(self, value):\n"
                  f"        self.__fields__[{name!r}] = value\n")
    out.write("\n")


def pygen_defs(sys_or_cls, out, done=None):
    if isinstance(sys_or_cls, BaseStruct):
        cls = sys_or_cls.__class__
    elif issubclass(sys_or_cls, BaseStruct):
        cls = sys_or_cls
    else:
        return
    if done is None:
        done = set()
    if cls.__name__ not in done:
        done.add(cls.__name__)
        pygen_class(cls, out)
    for field in cls.__dataclass_fields__.values():
        base = Field(field.type, cls).base
        if issubclass(base, BaseStruct) and base.__name__ not in done:
            done.add(base.__name__)
            pygen_defs(base, out, done)
            pygen_class(base, out)
        elif isinstance(base, EnumType) and base.__name__ not in done:
            pygen_enum(base, out)


def _search_funcs(obj, path):
    for fname, field in obj.__dataclass_fields__.items():
        ftype = Field(field.type)
        value = getattr(obj, fname)
        if ftype.func:
            if ftype.array:
                for idx, val in enumerate(value):
                    yield path + [(fname, idx, ftype, val)]
            else:
                yield path + [(fname, None, ftype, value)]
        elif issubclass(ftype.base, BaseStruct):
            if ftype.array:
                for idx, sub in enumerate(value):
                    if sub is not None:
                        yield from _search_funcs(sub,
                                                 path + [(fname, idx, ftype)])
            else:
                yield from _search_funcs(value, path + [(fname, None, ftype)])


def pygen_methods(system, out):
    for *path, (funcname, funcidx, functype, funcsrc) in _search_funcs(system, []):
        argnames = tuple(t.base.__name__.lower() for _, _, t in path)
        obj, env = system, system._env
        argsvals = ["system"]
        for (fname, idx, _) in path:
            if idx is None:
                argsvals.append(f"{argsvals[-1]}.{fname}")
                obj = getattr(obj, fname)
            else:
                argsvals.append(f"{argsvals[-1]}.{fname}[{idx}]")
                obj = getattr(obj, fname)[idx]
            env |= obj._env
        out.write(f"def _make({', '.join(argnames)}):\n")
        for k, v in env.items():
            if callable(v):
                out.write(inspect.getsource(v))
            else:
                out.write(f"    {k} = {v!r}\n")
        if func_def.match(funcsrc):
            for line in funcsrc.splitlines():
                out.write(f"    {line}\n")
        else:
            out.write(f"    def {funcname}():\n")
            if functype.base is type(None):
                out.write(f"        {funcsrc}\n")
            else:
                out.write(f"        return {functype.base.__name__}"
                          f"({funcsrc})\n")
        if funcidx is None:
            out.write(f"    {argnames[-1]}.{funcname} = {funcname}\n")
        else:
            out.write(f"    {argnames[-1]}.{funcname}[{funcidx}]"
                      f" = {funcname}\n")
        out.write(f"_make({', '.join(argsvals[1:])})\n\n")
    out.write("del _make\n")


def pygen_system(system, out):
    code = f"system = {system!r}"
    out.write(subprocess.check_output(["black", "-c", code],
                                      encoding="utf-8").rstrip())
    out.write("\n\n")


class tree (object):
    def __init__(self, label, state={}):
        self.label = label
        self.children = []
        for key, val in state.items():
            if isinstance(val, State):
                self.children.append(tree(key, val))
            elif (isinstance(val, tuple)
                  and isinstance(val[0], State)):
                self.children.extend(tree(f"{F.BLUE}{key}"
                                          f"{F.GREEN}[{n}]{F.RESET}", v)
                                     for n, v in enumerate(val))
            elif isinstance(val, tuple):
                self.children.append(tree(f"{F.BLUE}{key}:{F.RESET}"
                                          f" {list(val)}"))
            else:
                self.children.append(tree(f"{F.BLUE}{key}:{F.RESET}"
                                          f" {val}"))

    def print(self, out, prefix=None, last=True):
        if prefix is None:
            out.write(f"{self.label}\n")
        elif last:
            out.write(f" {prefix}{F.WHITE}└─{F.RESET} {self.label}\n")
        else:
            out.write(f" {prefix}{F.WHITE}├─{F.RESET} {self.label}\n")
        for child in self.children:
            if prefix is None:
                child.print(out, "", child is self.children[-1])
            elif last:
                child.print(out, prefix + "   ", child is self.children[-1])
            else:
                child.print(out, prefix + f"{F.WHITE}│{F.RESET}  ",
                            child is self.children[-1])

    def __str__(self):
        out = io.StringIO()
        self.print(out)
        return out.getvalue().rstrip()


def diff(old_state, new_state):
    ret = {}
    for key, old in old_state.items():
        new = new_state[key]
        if new == old:
            continue
        elif isinstance(old, State):
            if d := diff(old, new[key]):
                ret[key] = d
        elif (isinstance(old, tuple)
              and isinstance(old[0], State)):
            if t := tuple(d for o, v in zip(old, new) if (d := diff(o, v))):
                ret[key] = t
        else:
            ret[key] = new
    return State(old_state.struct, ret)


class Simulator:
    def __init__(self):
        self.initial = self.get_state()

    def get_state(self):
        return State(system, self._get_state(system))

    def _get_state(self, obj):
        fields = {}
        for key in obj.__state__:
            val = getattr(obj, key)
            if isinstance(val, tuple):
                st = tuple(self._get_state(v) for v in val)
                if not st or all(s is None for s in st):
                    st = None
                elif hasattr(val[0], "__state__"):
                    st = tuple(State(v, s) for v, s in zip(val, st))
            elif isinstance(val, list):
                st = tuple(val)
            elif hasattr(val, "__state__"):
                st = State(val, self._get_state(val)) or None
            else:
                st = val
            if st is not None:
                fields[key] = st
        return fields or None

    def set_state(self, state):
        self._set_state(state, system)

    def _set_state(self, state, obj):
        for key in obj.__state__:
            if key not in state:
                continue
            old, new = getattr(obj, key), state[key]
            if isinstance(old, tuple):
                for child, st in zip(old, new):
                    self._set_state(st, child)
            elif isinstance(old, list):
                getattr(obj, key)[:] = new
            elif hasattr(old, "__state__"):
                self._set_state(new, old)
            else:
                setattr(obj, key, new)

    @property
    def state(self):
        return self.get_state()

    @state.setter
    def state(self, state):
        self.set_state(state)

    def succ(self, state=None):
        old = self.get_state()
        if state is None:
            state = old
        for nnum, node in enumerate(system.nodes):
            for tnum, trans in enumerate(node.locations[node.current].transitions):
                self.set_state(state)
                if trans.guard():
                    cost = trans.cost()
                    trans.update()
                    yield (self.get_state(),
                           ("nodes", nnum, "locations", node.current,
                            "transitions", tnum),
                           cost)
        self.set_state(old)

    def _print_step(self):
        if not self.trace:
            return
        state, trans, cost = self.trace[-1]
        if trans is not None:
            path = ".".join(f"{f}[{i}]" for f, i in zip(trans[0::2],
                                                        trans[1::2]))
            print(f"{F.RED}fired system.{path} {S.DIM}(+${cost}"
                  f" => ${self.cost}){S.RESET_ALL}")
        print(tree(f"{F.RED}state #{len(self.trace)-1}{S.RESET_ALL}", state))

    def run(self, ask=True, count=None, start=None):
        state = start or self.initial
        self.trace = [(state, None, 0)]
        seen = set()
        self.cost = 0
        self._print_step()
        while count != 0:
            self.set_state(self.trace[-1][0])
            succs = list(self.succ())
            if not succs:
                print(f"{F.RED}### deadlock{F.RESET}")
                if not ask:
                    break
            if ask:
                if not self.ask(succs):
                    break
            else:
                step = secrets.choice(succs)
                if count is None and step in seen:
                    print(f"{F.RED}### loop found{F.RESET}")
                    count = 1
                self.trace.append(step)
                self.cost += self.trace[-1][2]
            seen.add(self.trace[-1])
            self._print_step()
            if count is not None:
                count -= 1

    def ask(self, succs):
        for num, (state, trans, cost) in enumerate(succs):
            small = diff(self.trace[-1][0], state)
            path = ".".join(f"{f}[{i}]" for f, i in zip(trans[0::2],
                                                        trans[1::2]))
            if small:
                print(tree(f"{F.YELLOW}[{num}] system.{path}"
                           f" {S.DIM}+${cost}{S.RESET_ALL}"
                           f" {S.DIM}(diff){S.RESET_ALL}", small))
            else:
                print(f"{F.YELLOW}[{num}] system.{path}"
                      f" {S.DIM}+${cost}{S.RESET_ALL}"
                      f" (same state)")
        while True:
            default = "r"
            if len(succs) == 0:
                prompt = f"{S.DIM}b(ack)|{S.RESET_ALL}q(quit)"
                default = "q"
            elif len(succs) == 1:
                prompt = f"0{S.DIM}|b(ack)|q(quit){S.RESET_ALL}"
            elif len(succs) == 2:
                prompt = (f"{S.DIM}0|1|b(ack)|q(quit)|"
                          f"{S.RESET_ALL+S.DIM}r(andom){S.RESET_ALL}")
            else:
                prompt = (f"{S.DIM}0|...|{len(succs)-1}|b(ack)|q(quit)|"
                          f"{S.RESET_ALL+S.DIM}r(andom){S.RESET_ALL}")
            prompt = f"{S.DIM}[{S.RESET_ALL}{prompt}{S.DIM}]{S.RESET_ALL} "
            try:
                resp = input(prompt).strip().lower() or default
            except Exception:
                resp = "quit"
            if resp[0] == "r":
                self.trace.append(secrets.choice(succs))
                self.cost += self.trace[-1][2]
                return True
            elif resp[0] == "q":
                return False
            elif resp[0] == "b":
                if len(self.trace) > 1:
                    self.cost -= self.trace[-1][2]
                    self.trace.pop(-1)
                return True
            else:
                try:
                    self.trace.append(succs[int(resp)])
                    self.cost += self.trace[-1][2]
                    return True
                except Exception:
                    pass


def pygen_ui(out):
    for line in inspect.getsourcelines(State)[0]:
        if "# CUT #" in line:
            break
        out.write(line)
    out.write("\n")
    out.write(inspect.getsource(tree) + "\n")
    out.write(inspect.getsource(diff) + "\n")
    out.write(inspect.getsource(Simulator))
    out.write("\n"
              "if __name__ == '__main__':\n"
              "    sim = Simulator()\n"
              "    sim.run()\n")


def pygen(system, out):
    pygen_headers(out)
    out.write("##\n## classes and enums definitions\n##\n\n")
    pygen_defs(system, out)
    out.write("##\n## system instance\n##\n\n")
    pygen_system(system, out)
    out.write("##\n## methods definitions with specific contexts\n##\n\n")
    pygen_methods(system, out)
    out.write("\n##\n## user interface\n##\n\n")
    pygen_ui(out)


if __name__ == "__main__":
    import argparse
    import importlib
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", type=argparse.FileType("w"),
                        default="-", metavar="PATH",
                        help="output path")
    parser.add_argument("struct", metavar="CLASS", type=str,
                        help="class to load")
    parser.add_argument("spec", nargs=2, metavar="SPEC",
                        help="paths for a Python/JSON system")
    args = parser.parse_args()
    *modname, classname = args.struct.split(".")
    modname = ".".join(modname)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception:
        parser.exit(2, f"could not import '{modname}.{classname}'\n")
    spec = {p.rsplit(".", 1)[-1].lower(): p for p in args.spec}
    try:
        system = cls.from_json(open(spec["json"]), spec["py"])
    except KeyError as err:
        parser.exit(2, f"no '.{err.args[0]}' file in"
                    f" {args.spec[0]!r}, {args.spec[1]!r}\n")
    pygen(system, args.out)
