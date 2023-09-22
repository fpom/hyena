import subprocess, importlib
from inspect import isclass
from pathlib import Path
from . import ena
from . import Field

def class_dot(out, root, gvopt):
    out.write("digraph {\n"
              "  node [shape=plaintext margin=0]\n"
              f"  {gvopt['graph']}\n")
    links = set()
    todo = [root]
    seen = {root.__name__} | {c.__name__ for c in root.__bases__}
    while todo and (cls := todo.pop()):
        classname = cls.__name__
        seen.add(classname)
        text = {"name": classname, True: [], False: []}
        if issubclass(cls, ena.Struct):
            color = "lightyellow"
            for name, field in cls.__dataclass_fields__.items():
                ftype = Field(field.type)
                text[ftype.prime].append(f"{'-' if ftype.const else '+'} {name}: "
                                         + f"{ftype}"[6 if ftype.const else 0:])
                if issubclass(ftype.base, ena.Struct) or isinstance(ftype.base, ena.EnumType):
                    succ = ftype.base.__name__
                    links.add((classname, succ))
                    if succ not in seen:
                        todo.append(getattr(ena, succ))
                        seen.add(succ)
        elif issubclass(cls, ena.StrEnum):
            color = "azure"
            text[False].extend(f"{num}: {val}" for num, val in enumerate(v.name for v in cls))
            del text[True]
        else:
            continue
        label = (f'<<FONT face="mono">'
                 f'<TABLE border="0" cellborder="1" cellspacing="0">'
                 f'<TR><TD bgcolor="{color}"><B>{text["name"]}</B></TD></TR>')
        if True in text:
            label += f'<TR><TD align="LEFT" balign="LEFT">{"<BR/>".join(text[True])}</TD></TR>'
        label += (f'<TR><TD align="LEFT" balign="LEFT">{"<BR/>".join(text[False])}</TD></TR>'
                  f'</TABLE>'
                  f'</FONT>>')
        out.write(f'  {classname} [label={label}] ;\n')
    for src, tgt in links:
        out.write(f' "{src}" -> "{tgt}" ;\n')
    out.write("}\n")

def object_dot(out, root, gvopt):
    out.write("digraph {\n"
              "  ranksep=1;"
              "  compound=true\n"
              f"  {gvopt['graph']}\n")
    current = {}
    for nnum, node in enumerate(root.nodes):
        current[nnum] = node.current
        out.write(f"  subgraph cluster_{nnum} {{\n"
                  f"    {gvopt['cluster']}\n"
                  f'    label=<<FONT face="mono">node #{nnum}</FONT>>;\n')
        for lnum, loc in enumerate(node.locations):
            status = loc.status[0].upper() if hasattr(loc, "status") else lnum
            attrs = f'shape=circle label=<<FONT face="mono">{status}</FONT>>'
            if lnum == node.current:
                attrs += 'style=filled fillcolor="#FFFFAA"'
            out.write(f"    loc_{nnum}_{lnum} [{attrs}]\n")
            for trans in loc.outputs:
                out.write(f"    loc_{nnum}_{lnum} -> loc_{nnum}_{trans.target}\n")
        out.write("  }\n")
    for nnum, node in enumerate(root.nodes):
        for pred in node.inputs:
            out.write(f'  loc_{pred.node}_{current[pred.node]} -> loc_{nnum}_{current[nnum]} [ltail="cluster_{pred.node}" lhead="cluster_{nnum}"]\n')
    out.write("}\n")

def draw(path, what=ena.System, **gvopt):
    path = Path(path)
    with path.with_suffix(".dot").open("w") as out:
        if isclass(what):
            class_dot(out, what, gvopt)
        else:
            object_dot(out, what, gvopt)
    if path.suffix != ".dot":
        subprocess.run(["dot",
                        "-T", path.suffix.lstrip("."),
                        "-o", str(path),
                        path.with_suffix(".dot")])
        path.with_suffix(".dot").unlink()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", type=str, default=None, metavar="PATH",
                        help="output path")
    parser.add_argument("-g", "--graph", type=str, default="", metavar="DOTOPT",
                        help="provide GraphViz options to be inserted at graph level")
    parser.add_argument("-c", "--cluster", type=str, default="", metavar="DOTOPT",
                        help="provide GraphViz options to be inserted at clusters (subgraphs) level")
    parser.add_argument("struct", metavar="CLASS", type=str,
                        help="draw CLASS (or an instance if SPEC is given)")
    parser.add_argument("spec", nargs="*", metavar="SPEC", 
                        help="paths for a Python/JSON system")
    args = parser.parse_args()
    *modname, classname = args.struct.split(".")
    if not args.out:
        args.out = f"{'_'.join(modname)}_{classname}.pdf"
    modname = ".".join(modname)
    try:
        ena = importlib.import_module(modname)
        cls = getattr(ena, classname)
    except Exception as err:
        parser.exit(2, (f"could not import '{modname}.{classname}'"
                        f" ({err.__class__.__name__}: {err})\n"))
    if len(args.spec) == 0:
        what = cls
    elif len(args.spec) == 2:
        src = {p.rsplit(".", 1)[-1].lower(): p for p in args.spec} 
        try:
            what = cls.from_json(open(src["json"]), src["py"])
        except KeyError as err:
            parser.exit(2, f"no '.{err.args[0]}' file in {args.spec[0]!r}, {args.spec[1]!r}\n")
    else:
        parser.print_usage()
        parser.exit(1, "expected two arguments for SPEC\n")
    draw(args.out, what, graph=args.graph, cluster=args.cluster)
