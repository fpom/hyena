import importlib.util as imputil
import json
import logging
import types
import re

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum as _StrEnum
from inspect import getmembers, getmodule, getsource, isclass, isfunction
from collections.abc import Callable
from typing import Annotated, Optional, Union, Any, Self, get_args, get_origin

from frozendict import frozendict

#
# logging
#


def make_logger(name, level=logging.DEBUG):
    log = logging.getLogger(name)
    log.setLevel(level)
    fmt = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
    han = logging.StreamHandler()
    han.setFormatter(fmt)
    log.addHandler(han)
    return log


log = make_logger("hyena")


#
# auxiliary stuff
#


class array(list):
    "fixed-length lists storing values of a specific type"
    def __init__(self, basetype, *largs, **kargs):
        super().__init__(basetype(v) for v in list(*largs, **kargs))
        self.__basetype__ = basetype

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
        if isinstance(index, slice):
            super().__setitem__(index, (self.__basetype__(v) for v in value))
        else:
            super().__setitem__(index, self.__basetype__(value))

    def __iadd__(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")

    def __imul__(self, _):
        raise TypeError(f"'{self.__class__.__name__}'"
                        f" object does not support length change")


#
# structures' fields description
#


class F(dict):
    annot = {
        "array": False,   # array of .base
        "index": None,    # index of .index or an array indexed by .index
        "func": False,    # function returning .base
        "macro": None,    # macro evaluated at compile time
        "prime": False,   # semantically required
        "const": True,    # mutable if .const is True
        "option": False,  # optional
        "unique": None    # value is unique within given scope
    }

    @classmethod
    def INDEX(cls, array):
        return cls(index=array)

    @classmethod
    def PRIME(cls):
        return cls(prime=True)

    @classmethod
    def MUTABLE(cls):
        return cls(const=False)

    @classmethod
    def MACRO(cls, expr):
        return cls(macro=expr, func=True, const=True)

    @classmethod
    def UNIQUE(cls, scope):
        return cls(unique=scope)

    def __init__(self, hint=None, parent=None, **annot):
        for key in annot:
            if key not in self.annot:
                raise TypeError(f"unknown field annotation: {key}")
        return super().__init__(annot)


class Field:
    def __init__(self, hint, parent=None):
        if get_origin(hint) is Annotated:
            self.base, annot = get_args(hint)
        else:
            self.base, annot = hint, {}
        self.annot = F.annot | annot
        if get_origin(self.base) is Union:
            self.base, *rest = get_args(self.base)
            assert (rest == [None]) or (rest == [type(None)])
            self.annot["option"] = True
        if get_origin(self.base) is list:
            self.base = get_args(self.base)[0]
            self.annot["array"] = True
        if get_origin(self.base) is Callable:
            if not (args := get_args(self.base)):
                r = type(None)
            else:
                a, r = args
                assert a == []
                if r is None:
                    r = type(None)
            self.base = r
            self.annot["func"] = True
        if parent is not None and issubclass(self.base, Struct):
            self.base = getattr(getmodule(parent), self.base.__name__)

    def __getattr__(self, name):
        return self.annot[name]

    def __repr__(self):
        fields = (f'{k}: {v!r}' for k, v in self.annot.items())
        return f"Field[{', '.join(fields)}]"

    def __str__(self):
        if self.array:
            if self.index:
                text = f"[{self.base.__name__} {self.index}]"
            else:
                text = f"[{self.base.__name__}]"
        elif self.index:
            text = f"#{self.index}"
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


#
# Python templating
#


class Template:
    __tpl_fields__ = {}

    def __init_subclass__(cls):
        cls.__tpl_fields__ = {k: v for k, v in cls.__dict__.items()
                              if not k.startswith("_")}

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
# states and execution contexts
#


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


class Method:
    def __init__(self, name, source, ret):
        self.func = self._load_func(name, source, ret)
        self.name = name
        self.context = {}

    def __repr__(self):
        try:
            name = self.func.__qualname__
        except AttributeError:
            name = self.func.__name__
        if self.context is None:
            return repr(f"<method {name}>")
        else:
            return repr(f"<bound method {name}>")

    def bind(self, obj, context):
        self.context = context | {"self": obj}
        self.func = types.MethodType(self.func, obj)

    def __call__(self, *largs, **kwargs):
        self.func.__globals__.update(self.context)
        state = self.context["system"].state
        try:
            ret = self.func(*largs, **kwargs)
        except Abort:
            self.context["system"].state = state
            raise
        return ret

    def has_jump(self):
        return re.search(r"raise\s+Jump", getsource(self.func)) is not None

    def _load_func(self, name, data, ret):
        if isinstance(data, str) or (ret and isinstance(data, ret)):
            data = repr(data)
            if ret is type(None):
                src = (f"def {name}(self):\n"
                       f"    {data or 'pass'}\n")
            else:
                src = (f"def {name}(self):\n"
                       f"    return {ret.__name__}({data})\n")
            env = {}
            exec(src, env)
            return env[name]
        elif isfunction(data):
            return data
        else:
            raise TypeError(f"expected str of function but got {data!r}")

#
# base class for enums and structures
#


class StrEnum(_StrEnum):
    def __repr__(self):
        return f"{self.__class__.__name__}.{self}"


@dataclass
class Struct:
    __pydefs__: Any

    @classmethod
    def _fields(cls):
        for name, field in cls.__dataclass_fields__.items():
            if name != "__pydefs__":
                yield name, Field(field.type, cls)

    def __post_init__(self):
        self.__dict__["__extra__"] = {}
        self.__dict__["__fields__"] = {n: t for n, t in self._fields()}

    def __getattr__(self, name):
        try:
            return self.__dict__["__extra__"][name]
        except KeyError:
            raise AttributeError(f"'{self.__class__.__name__}' object has no"
                                 f" attribute '{name}'")

    def __setattr__(self, name, value):
        if hasattr(self, "__fields__") and name != "state":
            ftype = self.__fields__.get(name, None)
            fname = f"{self.__class__.__name__}.{name}"
            if ftype is None:
                raise TypeError(f"cannot assign non-field {fname}")
            elif ftype.const:
                raise TypeError(f"cannot assign const field {fname}")
        super().__setattr__(name, value)

    @classmethod
    def dummy(cls) -> Self:
        fields = {}
        for name, ftype in cls._fields():
            if ftype.option:
                obj = None
            elif isclass(ftype.base) and issubclass(ftype.base, Struct):
                obj = ftype.base.dummy()
            elif isclass(ftype.base) and issubclass(ftype.base, StrEnum):
                obj = ftype.base(next(iter(ftype.base)))
            elif ftype.func:
                def _dummy(*largs, **kargs):
                    pass
                obj = Method(name, _dummy, ftype.base)
            else:
                obj = ftype.base()
            if not ftype.option and ftype.array:
                obj = (obj,) * 3
            fields[name] = obj
        return cls(__pydefs__=None, **fields)

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
        return cls._load(data, pydefs)

    @classmethod
    def _load(cls, data, pydefs):
        # build instance from available fields
        fields = {}
        for name, ftype in cls._fields():
            # load field
            if ftype.macro:
                fields[name] = Method(name, ftype.macro, ftype.base)
            elif name in data:
                fields[name] = cls._load_dict(name, data[name], ftype, pydefs)
            elif ftype.prime:
                raise ValueError(f"missing {cls.__name__}.{name} in {data}")
            else:
                fields[name] = None
                text = f"missing {cls.__name__}.{name} in {data}"
                if len(text) > 60:
                    text = text[:60] + "..."
                log.warn(text)
            # collect enums to be inserted in context
        struct = cls(**fields, __pydefs__=pydefs)
        # load extra fields from pydefs
        if pydefs and (tpl := getattr(pydefs, cls.__name__, None)) is not None:
            for key, val in getmembers(tpl):
                if (not key.startswith("_")
                        and key not in cls.__dataclass_fields__):
                    struct.__extra__[key] = val
        # load extra fields from data
        for key, val in data.items():
            if key not in cls.__dataclass_fields__:
                struct.__extra__[key] = val
        return struct

    @classmethod
    def _load_dict(cls, name, data, ftype, pydefs):
        if isinstance(ftype, Field):
            if ftype.array:
                if ftype.option and data is None:
                    return None
                items = (cls._load_dict(f"{name}_{i}", d, ftype.base, pydefs)
                         for i, d in enumerate(data))
                if ftype.const:
                    return tuple(items)
                else:
                    return array(ftype.base, items)
            elif ftype.func:
                if data is None:
                    return None
                else:
                    return Method(name, data, ftype.base)
            elif data is None and ftype.option:
                return None
            else:
                return cls._load_dict(name, data, ftype.base, pydefs)
        elif isclass(ftype):
            if issubclass(ftype, Struct):
                return ftype.from_dict(data, pydefs)
            elif issubclass(ftype, StrEnum):
                return getattr(ftype, data)
            elif isinstance(data, ftype):
                return data
        raise TypeError(f"could not load {ftype} from {data!r}")

    def _bind_methods(self, env=None):
        if env is None:
            env = {}
            if self.__pydefs__ is not None:
                env.update((k, v) for k, v in getmembers(self.__pydefs__)
                           if not k.startswith("_"))
        env |= {self.__class__.__name__.lower(): self}
        for fname, ftype in self._fields():
            value = getattr(self, fname)
            if issubclass(ftype.base, Struct):
                if isinstance(value, tuple):
                    for val in value:
                        if val is not None:
                            val._bind_methods(env)
                elif value is not None:
                    value._bind_methods(env)
            elif ftype.func or ftype.macro:
                if isinstance(value, tuple):
                    for val in value:
                        if val is not None:
                            val.bind(self, env)
                    if ftype.macro:
                        new = tuple(None if val is None else val()
                                    for val in value)
                        self.__dict__["fname"] = new
                elif value is not None:
                    value.bind(self, env)
                    if ftype.macro:
                        self.__dict__[fname] = value()
        for key, val in self.__extra__.items():
            if isfunction(val):
                meth = self.__extra__[key] = Method(val.__name__, val, None)
                meth.bind(self, env)

    @property
    def state(self):
        state = {}
        for name, ftype in self._fields():
            value = getattr(self, name)
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
        return State(self, state) or None

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
                raise ValueError(f"invalid object path {path!r}")
        return obj


class Jump(Exception):
    def __init__(self, cost, jumps):
        super().__init__()
        self.cost = cost
        self.jumps = {int(k): int(v) for k, v in jumps.items()}


class Abort(Exception):
    pass
