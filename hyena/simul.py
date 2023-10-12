import io
import re
import readline
import shlex
import inspect
import secrets
import importlib

from . import State
from colorama import Fore as F, Style as S, Back as B
from dataclasses import dataclass
from typing import Optional


readline.parse_and_bind("tab: complete")


class tree (object):
    def __init__(self, label, state={}):
        self.label = label
        self.children = []
        for key, val in state.items():
            if isinstance(val, State):
                self.children.append(tree(key, val))
            elif isinstance(val, tuple) and all(v is None for v in val):
                pass
            elif (isinstance(val, tuple)
                  and any(isinstance(v, State) for v in val)):
                self.children.extend(tree(f"{F.BLUE}{key}"
                                          f"{F.GREEN}[{n}]{F.RESET}", v)
                                     for n, v in enumerate(val)
                                     if v is not None)
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
            t = tuple(d if (d := diff(o, v)) else None
                      for o, v in zip(old, new))
            if any(x is not None for x in t):
                ret[key] = t
        else:
            ret[key] = new
    return State(old_state.struct, ret)


class Trans(tuple):
    def __str__(self):
        return ".".join(f"{f}[{i}]" for f, i in zip(self[0::2], self[1::2]))


@dataclass
class Event:
    state: State
    trans: Optional[Trans]
    cost: int


class Simulator:
    def __init__(self, system):
        self.sys = system
        self.ini = self.sys.state
        self.trace = [Event(self.ini, None, 0)]
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._complete)
        self._cmdhelp, self._cmdargs = {}, {}
        for name, meth in inspect.getmembers(self.__class__):
            if not name.startswith("_cmd_") or not callable(meth):
                continue
            name = name[5:]
            self._cmdhelp[name] = self._md(inspect.getdoc(meth))
            sig = inspect.signature(meth)
            argmax = len(sig.parameters) - 1
            argmin = len([n for n, p in sig.parameters.items()
                          if n != "self"
                          and p.default == inspect.Signature.empty])
            self._cmdargs[name] = (argmin, argmax)

    def _complete(self, text, state):
        match = [name for name in self._cmdhelp if name.startswith(text)]
        match.extend(idx for num in range(len(self.events))
                     if (idx := str(num)).startswith(text))
        if state is None:
            return match
        else:
            try:
                return match[state]
            except IndexError:
                pass

    @property
    def cost(self):
        return sum(e.cost for e in self.trace)

    @property
    def last(self):
        return self.trace[-1]

    def _print_event(self, index):
        event = self.trace[index]
        if event.trans is None:
            print(f"{F.RED}>>> init {S.DIM}(${self.cost}){S.RESET_ALL}")
        else:
            print(f"{F.RED}>>> system.{event.trans} {S.DIM}(+${event.cost}"
                  f" => ${self.cost}){S.RESET_ALL}")
        print(tree(f"{F.RED}#{index}{S.RESET_ALL}", event.state))

    def _print_last(self):
        self._print_event(len(self.trace) - 1)

    def _print_succs(self):
        if len(self.events) == 0:
            print(f"{F.RED}### deadlock{F.RESET}")
        else:
            last = self.trace[-1]
            for num, evt in enumerate(self.events):
                small = diff(last.state, evt.state)
                if small:
                    print(tree(f"{F.YELLOW}[{num}] system.{evt.trans}"
                               f" {S.DIM}+${evt.cost}{S.RESET_ALL}"
                               f" {S.DIM}(diff){S.RESET_ALL}", small))
                else:
                    print(f"{F.YELLOW}[{num}] system.{evt.trans}"
                          f" {S.DIM}+${evt.cost}{S.RESET_ALL}"
                          f" (same state)")

    def _long_prompt(self):
        self._print_last()
        self.events = [Event(s, Trans(t), c)
                       for s, t, c in self.sys.succ(self.last.state)]
        self._print_succs()

    def _expand_cmd(self, prefix):
        candidates = [c for c in self._cmdhelp if c.startswith(prefix)]
        if len(candidates) == 1:
            return candidates[0]
        else:
            return prefix

    def _read_cmd(self):
        prompt = f"{F.YELLOW}#{len(self.trace)}?{F.RESET} "
        try:
            line = input(prompt)
        except EOFError:
            print()
            print(f"{S.DIM}{prompt}quit{S.RESET_ALL}")
            line = "quit"
        except KeyboardInterrupt:
            print()
            line = "pass"
        if not line.strip():
            if self.events:
                line = "random"
            else:
                line = "tail"
            print(f"{S.DIM}{prompt}{line}{S.RESET_ALL}")
        cmd, *args = shlex.split(line)
        if not args and cmd[0] in "0123456789":
            cmd, args = "fire", [cmd]
        return self._expand_cmd(cmd), args

    def run(self):
        self._long_prompt()
        while True:
            while True:
                cmd, args = self._read_cmd()
                handler = getattr(self, f"_cmd_{cmd}", None)
                if handler is None:
                    self._print(f"{F.MAGENTA}###{F.RESET}"
                                f" unknown command `{cmd}`")
                    continue
                argmin, argmax = self._cmdargs[cmd]
                if not argmin <= len(args) <= argmax:
                    if argmin == argmax == 1:
                        self._print(f"{F.MAGENTA}###{F.RESET}"
                                    f" `{cmd}` expects 1 argument"
                                    f" but {len(args)} given")
                    elif argmin == argmax:
                        self._print(f"{F.MAGENTA}###{F.RESET}"
                                    f" `{cmd}` expects {argmin} arguments"
                                    f" but {len(args)} given")
                    else:
                        self._print(f"{F.MAGENTA}###{F.RESET}"
                                    f" `{cmd}` expects {argmin} to {argmax}"
                                    f" arguments but {len(args)} given")
                    continue
                break
            try:
                handler(*args)
            except KeyboardInterrupt:
                break
            except Exception as err:
                print(f"{F.MAGENTA}###{F.RESET} {err}")

    _md_sub = [
        (re.compile(r"`(.*?)`"),
         f"{B.WHITE}\\1{B.RESET}"),
        (re.compile(r"^(\s+)([*-])(\s+)"),
         f"\\1{S.DIM}\\2{S.RESET_ALL}\\3"),
    ]

    def _md(self, text):
        lines = text.splitlines()
        for num, txt in enumerate(lines):
            for old, new in self._md_sub:
                txt = old.sub(new, txt)
            lines[num] = txt
        return "\n".join(lines)

    def _print(self, text, **opt):
        print(self._md(text), **opt)

    def _cmd_help(self, cmd=None):
        """print help about specified command (or all if none given)
        * `help` alone shows a short help about all command
        * `help cmd` shows detailed about command `cmd`
        """
        width = max(len(c) for c in self._cmdhelp)
        if cmd is None:
            for name, doc in sorted(self._cmdhelp.items()):
                summary, *_ = doc.splitlines()
                print(f"{F.BLUE}{name:<{width}}{S.RESET_ALL}  {summary}")
        else:
            cmd = self._expand_cmd(cmd)
            if cmd in self._cmdhelp:
                summary, *details = self._cmdhelp[cmd].splitlines()
                print(f"{F.BLUE}{cmd:<{width}}{S.RESET_ALL}  {summary}")
                if details:
                    print(" " + "\n ".join(details))
            else:
                raise ValueError(self._md(f"command `{cmd}` is unknown"))

    def _cmd_quit(self):
        "exit simulator"
        raise KeyboardInterrupt

    def _cmd_tail(self, count=1):
        "print last states in trace and possible successors"
        for num in reversed(range(int(count))):
            self._print_event(len(self.trace) - 1 - num)
        self._print_succs()

    def _cmd_random(self):
        "run a randomly chosen event"
        self.trace.append(secrets.choice(self.events))
        self._long_prompt()

    def _cmd_back(self, count=1):
        "go back one or more step"
        for _ in range(int(count)):
            if len(self.trace) == 1:
                raise ValueError("initial trace (no events)")
            drop = self.trace.pop(-1)
            print(f"{S.DIM}{F.RED}<<< system.{drop.trans}{S.RESET_ALL}")
        self._long_prompt()

    def _cmd_fire(self, num):
        "fire event `num`"
        self.trace.append(self.events[int(num)])
        self._long_prompt()

    def _cmd_pass(self):
        "do nothing"
        pass

    def _cmd_reset(self):
        "reset the trace to initial state"
        print(f"{S.DIM}{F.RED}<<< {len(self.trace) - 1} events{S.RESET_ALL}")
        self.trace = [Event(self.ini, None, 0)]
        self._long_prompt()


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
    args = parser.parse_args()
    modname, classname = args.cls.rsplit(".", 1)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        parser.exit(2, (f"could not import '{modname}.{classname}'"
                        f" ({err.__class__.__name__}: {err})\n"))
    system = cls.from_json(args.json, args.python)
    simul = Simulator(system)
    simul.run()
