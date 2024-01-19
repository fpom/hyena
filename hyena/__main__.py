import importlib
from pathlib import Path

from typing import Annotated, Optional
from typer import Typer, Option, Argument, Exit, FileTextWrite
from rich import print as pprint
from rich.console import Console
from rich.text import Text

from .draw import draw as hyena_draw
from .simul import Simulator
from .reach import AssertFailed, Explorer

app = Typer(context_settings={"help_option_names": ["-h", "--help"]})


#
# draw model or system
#


@app.command(help="draw a model or a system")
def draw(
    struct: Annotated[
        str,
        Argument(
            metavar="CLASS",
            help="CLASS to draw or instantiate")],
    python: Annotated[
        Optional[Path],
        Argument(
            metavar="PATH",
            help="Python template")] = None,
    json: Annotated[
        Optional[Path],
        Argument(
            metavar="PATH",
            help="JSON model")] = None,
    automata: Annotated[
        bool,
        Option("-a", "--automata",
               help="draw automata inside system nodes")] = False,
    graph: Annotated[
        Optional[str],
        Option(
            "-g", "--graph",
            metavar="DOTOPT",
            help="GraphViz options to be inserted at graph level")] = None,
    cluster: Annotated[
        Optional[str],
        Option(
            "-c", "--cluster",
            metavar="DOTOPT",
            help="GraphViz options to be inserted at clusters level")] = None,
    out: Annotated[
        Optional[Path],
        Option(
            "-o", "--out",
            metavar="PATH",
            help="output result to PATH"
        )] = None):
    *modname, classname = struct.split(".")
    modname = ".".join(modname)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        pprint(f"[red]error:[/]"
               f" could not import '{modname}.{classname}'"
               f" ({err.__class__.__name__}: {err})")
        raise Exit(2)
    if python and json:
        what = cls.from_json(json, python)
    elif python:
        pprint("[red]error:[/] missing JSON model")
        raise Exit(1)
    elif json:
        pprint("[red]error:[/] missing Python template")
        raise Exit(1)
    else:
        what = cls
    opts = {}
    if graph is not None:
        opts["graph"] = graph
    if automata:
        opts["automata"] = automata
    if cluster is not None:
        opts["cluster"] = cluster
    if not out:
        mod = "_".join(modname.split("."))
        if python and json:
            out = Path(f"{mod}_{classname}_{python.stem}_{json.stem}.pdf")
        else:
            out = Path(f"{mod}_{classname}.pdf")
    hyena_draw(out, what, **opts)


#
# interactive simulation
#


@app.command(help="simulate a system interactively")
def simul(
    python: Annotated[
        Optional[Path],
        Argument(
            metavar="PATH",
            help="Python template")],
    json: Annotated[
        Optional[Path],
        Argument(
            metavar="PATH",
            help="JSON model")],
    struct: Annotated[
        str,
        Argument(
            metavar="CLASS",
            help="CLASS to instantiate")] = "hyena.ena.System"):
    modname, classname = struct.rsplit(".", 1)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        pprint(f"could not import '{modname}.{classname}'"
               f" ({err.__class__.__name__}: {err})")
        raise Exit(2)
    system = cls.from_json(json, python)
    simul = Simulator(system)
    simul.run()


#
# reachability analysis
#


def state_text(state):
    txt = Text(str(state))
    txt.highlight_regex(r"\d+", "green")
    txt.highlight_regex(r"\w+(?=\[)", "blue bold")
    txt.highlight_regex(r"\w+(?=\=)", "blue")
    return txt


def get_status(explo):
    return (f"[green]{len(explo)}[/] state{'s' if len(explo) > 1 else ''}"
            f" explored ([green]+{len(explo.todo)}[/] to go)")


@app.command(help="compute and check the reachability graph")
def reach(
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
    with stdout.status(get_status(explorer)) as status:
        try:
            for state, succs in explorer:
                status.update(get_status(explorer))
                if verbose:
                    stdout.print(state_text(state),
                                 f"[dim]=> [green]+{len(succs)}[/]",
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

#
#
#


if __name__ == "__main__":
    app()
