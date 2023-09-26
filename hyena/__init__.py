import logging
import json
import re
import importlib.util as imputil

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum as _StrEnum, EnumType
from typing import Any, Self, get_origin, get_args, Annotated
from inspect import isclass, getmembers, isfunction, getmodule, getsourcelines
from frozendict import frozendict


#
# logging
#


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
f = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
h = logging.StreamHandler()
h.setFormatter(f)
log.addHandler(h)


#
# auxiliary stuff
#


class array(list):
    "fixed-length lists"
    def append(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def extend(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def clear(self):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def insert(self, *_):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def remove(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def __delitem__(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support item deletion")

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            if len(self[index]) != len(list(value)):
                raise TypeError(f"'{self.__class__.__name__}'"
                                f" object does not support length change")
        super().__setitem__(index, value)

    def __iadd__(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def __imul__(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")


#
# structures' fields description
#


class Field:
    def __class_getitem__(cls, arg):
        if isinstance(arg, tuple):
            base, annot = arg
        else:
            base, annot = arg, {}
        if get_origin(base) is Annotated:
            base, a = get_args(base)
            annot |= a
        return Annotated[base, annot]
    annot = {
        "within": None,   # field is .base constrained within .within
        "array": False,   # field is an array of .base
        "index": None,    # field is the index of an array .index
        "func": False,    # field is a function returning .base
        "macro": None,    # field is a macro evaluated at compile time
        "prime": False,   # field is semantically required
        "const": False,   # field is not mutable
        "option": False,  # field is optional
        "unique": None    # field valeu is unique within given scope
    }

    def __init__(self, hint, parent=None):
        self.base, annot = get_args(hint)
        self.annot = self.annot | annot
        if parent is not None and issubclass(self.base, Struct):
            self.base = getattr(getmodule(parent), self.base.__name__)

    def __getattr__(self, name):
        return self.annot[name]

    def __str__(self):
        if self.within:
            text = f"#{self.within}"
        elif self.array:
            if self.index:
                text = f"[{self.base.__name__} {self.index}]"
            else:
                text = f"[{self.base.__name__}]"
        elif self.func:
            if self.base is type(None):
                text = "()"
            else:
                text = f"({self.base.__name__})"
        elif self.macro:
            text = f"{self.base.__name__} = {self.macro}"
        elif isclass(self.base):
            text = self.base.__name__
        else:
            text = str(self.base)
        if self.option:
            text = f"?{text}"
        if self.const:
            text = f"const {text}"
        if self.unique:
            text = f"{text}!{self.unique}"
        return text


class Index:
    def __class_getitem__(cls, arg):
        return Field[int, {"within": arg}]


class Array:
    def __class_getitem__(cls, args):
        try:
            typ, idx = args
        except TypeError:
            typ, idx = args, None
        return Field[typ, {"array": True, "index": idx}]


class Expr:
    def __class_getitem__(cls, arg):
        return Field[arg, {"func": True}]


Stmt = Expr[None]


class Prime:
    def __class_getitem__(cls, arg):
        return Field[arg, {"prime": True}]


class Const:
    def __class_getitem__(cls, arg):
        return Field[arg, {"const": True}]


class Macro:
    def __class_getitem__(cls, arg):
        typ, expr = arg
        return Field[typ, {"macro": expr, "const": True}]


class Option:
    def __class_getitem__(cls, arg):
        return Field[arg, {"option": True}]


class Unique:
    def __class_getitem__(cls, arg):
        typ, scope = arg
        return Field[typ, {"unique": scope}]


#
# decorator for Python templating
#


def template(cls):
    def __init__(self, **args):
        self.__tpl_fields__ = self.__tpl_fields__.copy()
        self.__tpl_fields__.update(args)

    def __tpl_todict__(self):
        fields = {}
        for key, val in self.__tpl_fields__.items():
            if hasattr(val, "__tpl_fields__"):
                fields[key] = val.__tpl_todict__()
            elif (isinstance(val, (list, tuple))
                  and val
                  and hasattr(val[0], "__tpl_fields__")):
                fields[key] = type(val)(v.__tpl_todict__() for v in val)
            else:
                fields[key] = deepcopy(val)
        return fields

    cls.__init__ = __init__
    cls.__tpl_todict__ = __tpl_todict__
    cls.__tpl_fields__ = {k: v for k, v in cls.__dict__.items()
                          if not k.startswith("_")}
    return cls


def tplfuse(ref, tpl):
    if isinstance(ref, dict):
        assert isinstance(tpl, dict)
        new = {}
        for key in set(ref) | set(tpl):
            if key in ref and key in tpl:
                new[key] = tplfuse(ref[key], tpl[key])
            elif key in ref:
                new[key] = ref[key]
            else:
                new[key] = tpl[key]
        return new
    elif isinstance(ref, (list, tuple)):
        assert isinstance(tpl, (list, tuple))
        if not tpl:
            return ref
        elif not ref:
            return tpl
        else:
            assert len(ref) == len(tpl)
            return type(ref)(tplfuse(r, t) for r, t in zip(ref, tpl))
    elif not ref:
        return tpl
    else:
        return ref


#
# base class for data structures
#


func_def = re.compile(r"\Adef\s+(\S+)\s*\(\s*\)\s*:\s*$", re.M)


class State(frozendict):
    struct = None

    def __new__(cls, struct, *args, **kwargs):
        self = frozendict.__new__(cls, *args, **kwargs)
        self.__init__(*args, **kwargs)
        self.__dict__["struct"] = struct.__class__.__name__.lower()
        return self

    def __repr__(self):
        content = ", ".join(f"{k}={v!r}" for k, v in self.items())
        return f"{self.struct}[{content}]"
    # CUT # only the above code is included by pygen

    def _update_env(self, env):
        env = deepcopy(env)
        for val in env.values():
            if isfunction(val):
                val.__globals__.update(env)
        return env

    def _update_src(self, src, env=None):
        if match := func_def.match(src):
            func = match.group(1)
            if env is None:
                return src + f"\n{func}()\n"
            else:
                _env = {}
                exec(src, _env)
                env[func] = _env[func]
                return f"{func}()"
        else:
            return src

    def eval(self, expr, env):
        return eval(self._update_src(expr, env),
                    self._update_env(env))

    def exec(self, stmt, env):
        env = self._update_env(env)
        exec(self._update_src(stmt), env)
        return env[self.struct].state


#
# base class for enums and structures
#


class StrEnum(_StrEnum):
    def __repr__(self):
        return f"{self.__class__.__name__}.{self}"


@dataclass
class Struct:
    @classmethod
    def from_json(cls, source, pydefs=None) -> Self:
        "load structure from JSON"
        try:
            try:
                data = json.load(source)
            except Exception:
                data = json.load(open(source))
        except Exception:
            data = json.loads(source)
        if not isinstance(data, dict):
            raise ValueError(f"cannot load from {data}")
        return cls.from_dict(data, pydefs)

    @classmethod
    def from_dict(cls, data: dict[str, Any], pydefs=None) -> Self:
        "load structure from dict"
        if isinstance(pydefs, str):
            spec = imputil.spec_from_file_location("___pydefs", pydefs)
            if spec is None or spec.loader is None:
                raise ValueError(f"could not load {pydefs} as a Python module")
            pydefs = imputil.module_from_spec(spec)
            spec.loader.exec_module(pydefs)
        if (tpl := getattr(pydefs, cls.__name__, None)) is not None:
            data = tplfuse(data, tpl().__tpl_todict__())
        return cls._load_fields(data, pydefs)

    @classmethod
    def _load_fields(cls, data, pydefs):
        fields = {}
        for name, field in cls.__dataclass_fields__.items():
            ftype = Field(field.type, cls)
            if ftype.macro:
                fields[name] = ftype.macro
            elif name in data:
                fields[name] = cls._load_dict(data[name], ftype, pydefs)
            elif ftype.prime:
                raise ValueError(f"missing {cls.__name__}.{name} in {data}")
            else:
                fields[name] = None
                text = f"missing {cls.__name__}.{name} in {data}"
                if len(text) > 80:
                    text = text[:77] + "..."
                log.warn(text)
        struct = cls(**fields)
        if pydefs and (tpl := getattr(pydefs, cls.__name__, None)) is not None:
            for key, val in getmembers(tpl):
                if not key.startswith("_") and key not in cls.__dataclass_fields__:
                    struct._env[key] = val
        for key, val in data.items():
            if key not in cls.__dataclass_fields__:
                struct._env[key] = val
        for name, field in cls.__dataclass_fields__.items():
            ftype = Field(field.type, cls)
            if isinstance(ftype.base, EnumType):
                struct._env[ftype.base.__name__] = ftype.base
        return struct

    @classmethod
    def _load_dict(cls, data, ftype, pydefs):
        if isinstance(ftype, Field):
            if ftype.array:
                typ = tuple if ftype.const else array
                return typ(cls._load_dict(d, ftype.base, pydefs) for d in data)
            elif ftype.func:
                if isfunction(data):
                    return cls._funcsrc(data)
                else:
                    return data
            elif data is None and ftype.option:
                return None
            else:
                return cls._load_dict(data, ftype.base, pydefs)
        elif isclass(ftype):
            if issubclass(ftype, Struct):
                return ftype.from_dict(data, pydefs)
            elif issubclass(ftype, StrEnum):
                return getattr(ftype, data)
            elif isinstance(data, ftype):
                return data
        raise TypeError(f"could not load {ftype} from {data!r}")

    @classmethod
    def _funcsrc(cls, func):
        lines, indent = [], 0
        for line in getsourcelines(func)[0]:
            if not lines:
                indent = len(line) - len(line.lstrip())
                if not func_def.match(line.strip()):
                    raise ValueError(f"expected 'def ...():'"
                                     f" but got {line.strip()!r}")
            lines.append(line[indent:].rstrip())
        return "\n".join(lines)

    def _eval_macros(self, state=None, env=None):
        if state is None or env is None:
            state, env = self.state, {}
        env |= self.env
        for fname, field in self.__dataclass_fields__.items():
            ftype = Field(field.type)
            value = getattr(self, fname)
            if issubclass(ftype.base, Struct):
                if isinstance(value, tuple):
                    for val in value:
                        if val is not None:
                            val._eval_macros(state, env)
                elif value is not None:
                    value._eval_macros(state, env)
            elif ftype.macro:
                setattr(self, fname, state.eval(value, env))

    def __post_init__(self):
        self._env = {}

    @property
    def state(self):
        state = {}
        for name, field in self.__dataclass_fields__.items():
            value = getattr(self, name)
            ftype = Field(field.type)
            if (isinstance(value, Struct) and (st := value.state) is not None):
                state[name] = st
            elif isinstance(value, tuple):
                if value and isinstance(value[0], Struct):
                    st = tuple(v.state for v in value)
                    if any(s for s in st):
                        state[name] = st
            elif isinstance(value, list):
                state[name] = tuple(value)
            elif value is not None and not ftype.const:
                state[name] = value
        return State(self, state)

    @state.setter
    def state(self, new):
        if (me := self.__class__.__name__.lower()) != new.struct:
            raise ValueError(f"cannot assign {new} to {me}.state")
        for key, val in new.items():
            if isinstance(val, State):
                getattr(self, key).state = val
            elif isinstance(val, tuple) and val and isinstance(val[0], State):
                for s, v in zip(getattr(self, key), val):
                    s.state = v
            elif isinstance((old := getattr(self, key)), list):
                old[:] = val
            else:
                setattr(self, key, val)

    @property
    def env(self):
        name = self.__class__.__name__.lower()
        return self._env | {name: self}

    def __getitem__(self, path):
        if not isinstance(path, tuple):
            path = (path,)
        obj = self
        for p in path:
            if isinstance(p, str):
                obj = getattr(obj, p)
            elif isinstance(p, int):
                obj = obj[p]
            else:
                raise ValueError("invalid object path {path!r}")
        return obj
