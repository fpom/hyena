import ast, logging
import importlib.util as imputil

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum as _StrEnum, EnumType
from typing import Any, Self, get_origin, get_args, Annotated
from inspect import isclass, getmembers, isfunction, getmodule
from frozendict import frozendict

##
## auxiliary stuff
##

class array(list):
    "fixed-length lists"
    def append(self, *l, **k):
        raise TypeError("'array' object does not support length change")
    def extend(self, *l, **k):
        raise TypeError("'array' object does not support length change")
    def clear(self, *l, **k):
        raise TypeError("'array' object does not support length change")
    def insert(self, *l, **k):
        raise TypeError("'array' object does not support length change")
    def remove(self, *l, **k):
        raise TypeError("'array' object does not support length change")
    def __delitem__(self, item):
        raise TypeError("'array' object does not support item deletion")
    def __setitem__(self, index, value):
        if isinstance(index, slice):
            if len(self[index]) != len(list(value)):
                raise TypeError("'array' object does not support length change")
        super().__setitem__(index, value)
    def __iadd__(self, other):
        raise TypeError("'array' object does not support length change")
    def __imul__(self, other):
        raise TypeError("'array' object does not support length change")

##
## load JSON with Python comments inside
##

_json_const = {"true": True, "false": False, "null": None}

def json_loads(text):
    "this is `ast.literal_eval` extended with handling `false`/`true`/`null`"
    node = ast.parse(text.lstrip(" \t"), mode="eval")
    if isinstance(node, ast.Expression):
        node = node.body
    def _raise_malformed_node(node):
        msg = "malformed node or string"
        if lno := getattr(node, "lineno", None):
            msg += f" on line {lno}"
        raise ValueError(msg + f": {node!r}")
    def _convert_num(node):
        if not isinstance(node, ast.Constant) or type(node.value) not in (int, float, complex):
            _raise_malformed_node(node)
        return node.value
    def _convert_signed_num(node):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = _convert_num(node.operand)
            if isinstance(node.op, ast.UAdd):
                return + operand
            else:
                return - operand
        return _convert_num(node)
    def _convert(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Tuple):
            return tuple(map(_convert, node.elts))
        elif isinstance(node, ast.List):
            return array(map(_convert, node.elts))
        elif isinstance(node, ast.Set):
            return set(map(_convert, node.elts))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
              node.func.id == 'set' and node.args == node.keywords == []):
            return set()
        elif isinstance(node, ast.Dict):
            if len(node.keys) != len(node.values):
                _raise_malformed_node(node)
            return dict(zip(map(_convert, node.keys),
                            map(_convert, node.values)))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            left = _convert_signed_num(node.left)
            right = _convert_num(node.right)
            if isinstance(left, (int, float)) and isinstance(right, complex):
                if isinstance(node.op, ast.Add):
                    return left + right
                else:
                    return left - right
        elif isinstance(node, ast.Name):
            if node.id not in _json_const:
                _raise_malformed_node(node)
            return _json_const[node.id]
        return _convert_signed_num(node)
    return _convert(node)

##
## structures' fields description
##

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
        "within": None,  # field is .base constrained within .within
        "array": False,  # field is an array of .base
        "index": None,   # field is the index of an array .index
        "func": False,   # field is a function returning .base
        "macro": None,   # field is a macro evaluated at compile time
        "prime": False,  # field is semantically required
        "const": False,  # field is not mutable
        "option": False, # field is optional
        "unique": None   # field valeu is unique within given scope
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

##
## decorator for Python templating
##

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
        for key in set(ref)|set(tpl):
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

##
## base class for data structures
##

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
    #CUT# only the above code is included by pygen
    def _update_env(self, env):
        env = deepcopy(env)
        for val in env.values():
            if isfunction(val):
                val.__globals__.update(env)
        return env
    def eval(self, expr, env):
        return eval(expr, self._update_env(env))
    def exec(self, stmt, env):
        env = self._update_env(env)
        exec(stmt, env)
        return env[self.struct].state

##
## base class for enums and structures
##

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
                text = source.read()
            except:
                text = open(source).read()
        except :
            text = source
        data = json_loads(text)
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
        fields = {}
        for name, field in cls.__dataclass_fields__.items():
            ftype = Field(field.type, cls)
            if name in data:
                fields[name] = cls._load_dict(data[name], ftype, pydefs)
            elif ftype.prime:
                raise ValueError(f"missing {cls.__name__}.{name} in {data}")
            else:
                fields[name] = None
                text = f"missing {cls.__name__}.{name} in {data}"
                if len(text) > 80:
                    text = text[:77] + "..."
                logging.warn(text)
        struct = cls(**fields)
        struct._env = {}
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
    @property
    def state(self):
        state = {}
        for name, field in self.__dataclass_fields__.items():
            value = getattr(self, name)
            ftype = Field(field.type)
            if (isinstance(value, Struct)
                and (st := value.state) is not None):
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
        return self._env|{name: self}
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
