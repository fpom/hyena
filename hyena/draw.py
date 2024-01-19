import subprocess
import importlib
import enum

from inspect import isclass
from pathlib import Path
from . import ena


def class_dot(out, root, graph=""):
    out.write("digraph {\n"
              "  node [shape=plaintext margin=0]\n")
    if graph:
        out.write(f"  {graph}\n")
    links = set()
    todo = [root]
    seen = {root.__name__} | {c.__name__ for c in root.__bases__}
    while todo and (cls := todo.pop()):
        classname = cls.__name__
        seen.add(classname)
        text = {"name": classname, True: [], False: []}
        if issubclass(cls, ena.Struct):
            color = "lightyellow"
            for name, ftype in cls._fields():
                text[ftype.prime].append(
                    f"{'-' if ftype.const else '+'} {name}: "
                    + f"{ftype}"[6 if ftype.const else 0:])
                if (issubclass(ftype.base, ena.Struct)
                        or isinstance(ftype.base, enum.EnumType)):
                    succ = ftype.base.__name__
                    links.add((classname, succ))
                    if succ not in seen:
                        todo.append(getattr(ena, succ))
                        seen.add(succ)
        elif issubclass(cls, ena.StrEnum):
            color = "azure"
            text[False].extend(f"{num}: {val}"
                               for num, val in enumerate(v.name for v in cls))
            del text[True]
        else:
            continue
        label = (f'<<FONT face="mono">'
                 f'<TABLE border="0" cellborder="1" cellspacing="0">'
                 f'<TR><TD bgcolor="{color}"><B>{text["name"]}</B></TD></TR>')
        if True in text:
            label += (f'<TR><TD align="LEFT" balign="LEFT">'
                      f'{"<BR/>".join(text[True])}</TD></TR>')
        label += (f'<TR><TD align="LEFT" balign="LEFT">'
                  f'{"<BR/>".join(text[False])}</TD></TR>'
                  f'</TABLE>'
                  f'</FONT>>')
        out.write(f'  {classname} [label={label}] ;\n')
    for src, tgt in links:
        out.write(f' "{src}" -> "{tgt}" ;\n')
    out.write("}\n")


def object_dot(out, root, graph="", cluster="", automata=False):
    out.write("digraph {\n"
              "  ranksep=1;"
              "  compound=true\n")
    if graph:
        out.write(f"  {graph}\n")
    current = {}
    for nnum, node in enumerate(root.nodes):
        current[nnum] = node.current
        out.write(f"  subgraph cluster_{nnum} {{\n")
        if cluster:
            out.write(f"    {cluster}\n")
        out.write(f'    label=<<FONT face="mono">node #{nnum}</FONT>>;\n')
        for lnum, loc in enumerate(node.locations):
            if automata or lnum == node.current:
                status = (loc.status[0].upper()
                          if hasattr(loc, "status") else lnum)
                attrs = (f'shape=circle label=<<FONT face="mono">'
                         f'{status}</FONT>>')
                if lnum == node.current:
                    attrs += 'style=filled fillcolor="#FFFFAA"'
                out.write(f"    loc_{nnum}_{lnum} [{attrs}]\n")
                if automata:
                    for trans in loc.transitions:
                        if trans.action.has_jump():
                            attr = f' [arrowhead=dot color=darkred]'
                        else:
                            attr = ""
                        out.write(f"    loc_{nnum}_{lnum}"
                                  f" -> loc_{nnum}_{trans.target}"
                                  f"{attr}\n")
        out.write("  }\n")
    for nnum, node in enumerate(root.nodes):
        for pred in node.inputs:
            out.write(f'  loc_{pred.node}_{current[pred.node]}'
                      f' -> loc_{nnum}_{current[nnum]}'
                      f'[ltail="cluster_{pred.node}"'
                      f' lhead="cluster_{nnum}"]\n')
    out.write("}\n")


def draw(path, what=ena.System, **opts):
    global ena
    path = Path(path)
    with path.with_suffix(".dot").open("w") as out:
        if isclass(what):
            ena = importlib.import_module(what.__module__)
            class_dot(out, what, **opts)
        else:
            object_dot(out, what, **opts)
    if path.suffix != ".dot":
        subprocess.run(["dot",
                        "-T", path.suffix.lstrip("."),
                        "-o", str(path),
                        path.with_suffix(".dot")])
        path.with_suffix(".dot").unlink()
