import importlib.util as imputil
import json
import logging
import types
import re

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum as _StrEnum
from inspect import getmembers, getmodule, getsource, isclass, isfunction
from typing import Annotated, Any, Self, get_args, get_origin

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


class Field:
    annot = {
        "within": None,   # field is .base constrained within .within
        "array": False,   # field is an array of .base
        "index": None,    # field is the index of an array .index
        "func": False,    # field is a function returning .base
        "action": False,  # field is an action
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

    def __class_getitem__(cls, arg):
        if isinstance(arg, tuple):
            base, annot = arg
        else:
            base, annot = arg, {}
        if get_origin(base) is Annotated:
            base, a = get_args(base)
            annot |= a
        return Annotated[base, annot]

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


Action = Field[None, {"func": True, "action": True}]


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
# Python templating
#

class Dummy:
    def __getattr__(self, _):
        return self

    def __getitem__(self, _):
        return self

    def __delitem__(self, _):
        pass

    def __setattr__(self, _, __):
        pass

    def __setitem__(self, _, __):
        pass

    def __contains__(self, _):
        return True

    def __add__(self, _):
        return self

    def __sub__(self, _):
        return self

    def __mul__(self, _):
        return self

    def __div__(self, _):
        return self

    def __truediv__(self, _):
        return self

    def __floordiv__(self, _):
        return self

    def __pow__(self, _):
        return self

    def __mod__(self, _):
        return self

    def __lshift__(self, _):
        return self

    def __rshift__(self, _):
        return self

    def __and__(self, _):
        return self

    def __or__(self, _):
        return self

    def __xor__(self, _):
        return self

    def __neg__(self):
        return self

    def __pos__(self):
        return self

    def __abs__(self):
        return self

    def __invert__(self):
        return self

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __lt__(self, _):
        return True

    def __le__(self, _):
        return True

    def __eq__(self, _):
        return True

    def __ne__(self, _):
        return True

    def __gt__(self, _):
        return True

    def __ge__(self, _):
        return True

    def __bool__(self):
        return True

    def __call__(self, *_, **__):
        return self

    def __len__(self):
        return 0

    def __iter__(self):
        yield self


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
    def __init__(self, name, source, ret, action=False):
        self.func = self._load_func(name, source, ret)
        self.context = None
        self.action = action

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
        self.context = dict(context)
        self.func = types.MethodType(self.func, obj)

    def __call__(self, *largs, **kwargs):
        self.func.__globals__.update(self.context)
        if self.action:
            state = self.context["system"].state
        ret = self.func(*largs, **kwargs)
        if self.action and ret is None:
            self.context["system"].state = state
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
                    return Method(name, data, ftype.base, ftype.action)
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
                raise ValueError("invalid object path {path!r}")
        return obj


class Jump(Exception):
    def __init__(self, *seq, **idx):
        super().__init__()
        jumps = idx | {i: s for i, s in enumerate(seq) if s is not None}
        self.jumps = {int(k): int(v)
                      for k, v in jumps.items()
                      if v is not None}
