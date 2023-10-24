import collections
import importlib
import json

from .simul import Event, Trans

from typing import Annotated, Optional
from typer import Typer, Option, FileTextWrite, Exit
from rich.console import Console
from rich.text import Text


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
            for s, *_ in succ:
                if (s not in self.succ
                        and (self.limit is None
                             or len(self) < self.limit)):
                    self.todo.append(s)
                    self.succ[s] = None
            yield state, succ

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

    def status(self):
        return (f"[green]{len(self)}[/] state{'s' if len(self) > 1 else ''}"
                f" explored ([green]+{len(self.todo)}[/] to go)")


def state_text(state):
    txt = Text(str(state))
    txt.highlight_regex(r"\d+", "green")
    txt.highlight_regex(r"\w+(?=\[)", "blue bold")
    txt.highlight_regex(r"\w+(?=\=)", "blue")
    return txt


app = Typer(context_settings={"help_option_names": ["-h", "--help"]})


@app.command()
def main(
    json: Annotated[
        str,
        Option(
            "--json", "-j",
            metavar="PATH",
            help="JSON file to be loaded"
        )],
    python: Annotated[
        str,
        Option(
            "--python", "-p",
            metavar="PATH",
            help="Python template to be loaded"
        )],
    cname: Annotated[
        str,
        Option(
            "--class", "-c",
            metavar="CLASS",
            help="`System` class to be loaded"
        )] = "hyena.ena.System",
    verbose: Annotated[
        bool,
        Option(
            "--verbose", "-v",
            help="prints states as they are explored"
        )] = False,
    props: Annotated[
        list[str],
        Option(
            "--assert", "-a",
            help="properties to be checked on every state"
        )] = [],
    trace: Annotated[
        bool,
        Option(
            "--trace", "-t",
            help="print a trace to a state found violating assert"
        )] = False,
    save: Annotated[
        FileTextWrite,
        Option(
            "--save", "-s",
            metavar="PATH",
            help="save state-space as JSON to PATH"
        )] = None,
    limit: Annotated[
        Optional[int],
        Option(
            "--limit", "-l",
            metavar="NUM",
            help="limit exploration to NUM states"
        )] = None,
    depth: Annotated[
        bool,
        Option(
            "--depth", "-d",
            help="explore depth-first instead of the default breadth-first"
        )] = False):
    stdout, stderr = Console(), Console(stderr=True)
    modname, classname = cname.rsplit(".", 1)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        stderr.print(f"[red bold]error:[/] could not import",
                     f"'{modname}.{classname}'")
        stderr.print(f" :boom: [red]{err.__class__.__name__}[/]: {err}")
        raise Exit(2)
    system = cls.from_json(json, python)
    try:
        explorer = Explorer(system, depth, limit, props)
    except AssertFailed as err:
        stderr.print(f"[red bold]error:[/] invalid assertion '{err.prop}'")
        errname = err.err.__class__.__name__
        stderr.print(f" :boom: [red]{errname}[/]: {err.err}",
                     highlight=False)
        raise Exit(3)
    with stdout.status(explorer.status()) as status:
        try:
            import time
            for state, succs in explorer:
                status.update(explorer.status())
                time.sleep(1)
                if verbose:
                    stdout.print(state_text(state),
                                 f"=> [green]+{len(succs)}[/]",
                                 highlight=False)
        except KeyboardInterrupt:
            pass
        except AssertFailed as err:
            stdout.print(f"[red bold]assert failed[/] '{err.prop}'")
            if trace:
                for n, e in enumerate(explorer.trace(err.state)):
                    if e.trans is not None:
                        stdout.print(f"[dim]>>[/] [cyan]system.{e.trans}[/]",
                                     f"[dim]=>[/] [green]{e.action}[/green]",
                                     highlight=False)
                    stdout.print(f"[yellow]#{n}", state_text(e.state),
                                 highlight=False)
    if save is not None:
        explorer.save(save)


if __name__ == "__main__":
    app()
