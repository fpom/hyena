# Hybrid and Extensible Networks of Automata

`hyena` is a Python library to define and simulate (ie, execute) hybrid and extensible networks of automata (HyENA).
A HyENA consists of a collection of finite automata that execute on a network while sharing some data.
HyENAs are:

 * extensible in a least two ways:
   - adding data to the execution context
   - sub-classing the basic structures forming the basic HyENA model
 * hybrid in that a state is defined by:
   - the states of the automata
   - arbitrary additional data (possible updated by the system or its environment)

This document starts by presenting the concepts underlying `hyena` and then progressively moves to the concrete usage of the library and the associated command-line tools.

## Basic HyENA model

This basic model features 5 classes that can be seen as structures with predefined fields:

 * `System`: stores a full HyENA
 * `Node`: stores one automaton of a `System` instance
 * `Location`: stores one location (ie, state) of an automaton, we use the term _location_ in order to make a clear distinction with one state of the system
 * `Transition`: stores one transition between two locations
 * `Input`: stores an explicit link between two nodes (to form an explicit network)

 Although the network may be left implicit and `Input` is not strictly necessary, we prefer to have it in the basic model to emphasize the network dimension of HyENAs.

 These classes and their relations are illustrated here:

![the classes in the basic model](doc/ena.png)

For each class, its fields are listed either starting with a `-`, which means that the field is immutable, or starting with a `+`, which means that the filed may be updated during execution.
In this minimalistic model, only `Node.current` is mutable.
Each field also has a type, noted as follows:

 * atomic types are `bool`, `int`, possibly other Python types, and the classes defined above
 * `[T]` is a fixed-length array of instances of class `T` (eg, `System.nodes` is an array of `Node` instances); arrays are implemented as a `tuple` if immutable, or as a custom `array` class if mutable 
 * `#.F` is an index of field `.F` is the current class (eg, `Node.current` is an index of `Node.locations`)
 * `#T.F` is an index of field `.F` in class `T` (eg, `Input.node` is an index of `System.nodes`)
 * `()` is a function, it may have side effects on mutable fields, and may return a value, as explained below

Note that these types are currently loosely enforced in simulation, for instance, it is possible to set `Node.current` to a negative value, but this will lead to errors in the simulation.
So, even if it will be improved in future versions, currently it is mainly modeler's responsibility to respect the typing constraints.

The fields of each class are presented in two sections: the upper section lists the _primitive_ fields that are mandatory in every instance; the lower section lists the fields that can be omitted without impairing the capability to execute a system.
In other words: if a primitive field is missing, execution will fail; if a non-primitive field is missing, execution may succeed as long as the field is not used by this particular system.
This differs from optional fields (see below) that every system should consider as potentially missing.
In the basic model above, all the fields are primitive ones except for `Node.inputs`.

From the fields depicted above, we can describe more precisely each class of the basic model:

 * a `System` instance consists of an array of `Node` instances
 * a `Node` instance consists of:
   - an array of `Input` instances
   - an array of `Locations` instances
   - the index of the current location in this latter array
 * an `Input` consists of the number of a node that connects to this input (ie, if in `system` there is a link from node `a` to node `b`, then there is in `b.inputs` one `Input` value whose field `.node` is the index of `a` in `system.nodes`)
 * a `Location` consists of an array of `Transition` instances
 * a `Transition` consists of:
   - a `.target` location given as an index in the current node's `.locations` field
   - a `.action` that is a function, it may return a value to be recorded in the trace, it may also update the system by assigning some of its mutable fields

## Execution semantics

Let `system` be an instance of the `System` class as defined above.
Such a system is aimed at being executed, or simulated, that is: its transitions may be fired, depending on conditions, and leading to updates in the structures.
To describe such an executable semantics, `hyena` adopts the Python language as a concrete way to write and execute conditions and updates encoded into functions like `Transition.action`.
The execution semantics defines how transitions can be executed by making explicit in which context each such function is evaluated (following the usual rules of Python).

### System states

The state of a `System` instance is defined as the values that are stored within every mutable field of the system's objects.
This may be encoded as a Python `dict` representing the nesting of the structures.
For instance, assuming a system with 3 nodes, each with 2 locations, its state could be:

```python
{ # the state of system is the state of its nodes
    "nodes": [
        { # the state of node #0 is the value of its field .current
          # no other field of a Node has a state
            "current": 0
        },
        { # state of node #1
            "current": 0
        },
        { # state of node #2
            "current": 0
        }
    ]
}
```

This means that every node is in its first location.
Executing a transition in node `#2` that lead to location `#1` in this node may yield state:

```python
{"nodes": [{"current": 0}, {"current": 0}, {"current": 1}]}
```

In the implementation, such a state is implemented as a hashable frozen `dict` and is displayed in a more explicit way as:

```python
system[nodes=(node[current=0], node[current=0], node[current=1])]
```

The initial state of a system is its state when no transition has been executed yet, ie, this is the state that follows for the system's definition.

### Execution contexts

Every function is defined as the field of a class instance, itself stored within another class instance, and so on until we reach `System` instance.
In our minimal HyENA model, consider a very simple system with:

 * two nodes
 * each node is the input of the other one
 * each node has two locations 
 * each location has a transition to the other one
 * transitions execution have a cost that is `0` if the other node is in the same location as the one that executes the transition, or `1` otherwise

This system could be schematically drawn as follows:

![a very simple HyENA](examples/simple.png)

where each node is depicted as a rectangle within which its automaton is drawn, the current location of each one being `0`, highlighted in light yellow.

We focus on `Location.action` to understand how is can be executed.
Considering that our `System` instance is `system`, we have four actions:

 * `system.nodes[0].locations[0].transitions[0].action`
 * `system.nodes[0].locations[1].transitions[0].action`
 * `system.nodes[1].locations[0].transitions[0].action`
 * `system.nodes[1].locations[1].transitions[0].action`

Each of this function can be evaluated in a context that corresponds exactly to the "path" (ie, the nesting of structures) that allows to access it from `system`.
This is equivalent to defining four functions as follows:

```python
system = ...  # the System instance

def make_action(node, location, transition):
    # additional declarations may come here as explained later on 
    def action():
        .. # see below
    transition.action = action

make_action(system.nodes[0],
            system.nodes[0].locations[0],
            system.nodes[0].locations[0].transitions[0])
make_action(system.nodes[0],
            system.nodes[0].locations[1],
            system.nodes[0].locations[1].transitions[0])
make_action(system.nodes[1],
            system.nodes[1].locations[0],
            system.nodes[1].locations[0].transitions[0])
make_action(system.nodes[1],
            system.nodes[1].locations[1],
            system.nodes[1].locations[1].transitions[0])
```

In this code, the function `action` for each transition is defined within a closure that corresponds to its context, then it is assigned to the transition.
Consequently, each such function can access names `system`, `node`, `location`, `transition` that correspond to the path that lead to it.
Doing so, we can have the same body instead of `...` for all the functions:

```python
if node.current == system.nodes[node.inputs[0].node].current:
    return 0
else:
    return 1
```

In this code, `node` is not the same for every function, but `system` is unique.

To summarize, HyENAs' actions are defined in the scope of the objects that contain them: a node is in the scope of the system, a location is in the scope of its node, a transition is in the scope of its location, and an action is the scope of its transition.
These scopes are defined by the inclusion of one object into another, just like a Python scope, or closure, is defined by the inclusion of one function into another.
Actions will be implemented as methods of (subclasses of) `Transition`.
Auxiliary methods will be allowed for any class and their execution contexts will be defined exactly the same way.

### Transitions execution

Executing transitions allows building traces that are sequences of alternating states and transitions (with actions): starting from the initial state, a transition `t` may be executed if its action `t.action` returns a value `a` in the current execution context (`a` may be anything, including `None`).
But if `t.action` raises exception `Abort`, then the transition is forbidden.
Thus, `t.action` plays the role of both a guard and an update, which is usually devoted to two separate functions.
Having just one function is convenient to avoid recomputing things in the update things that have been computed in the guard.
So, after the `t.action` returned, all the assignments to mutable fields performed during its execution, as well as `node.current = t.target` to move to the expected location, are committed to the system.
This yields a new state `s` and the trace is extended with `(t,a), s`.

It is also possible to build a state graph that aggregates all the traces.
It is the smallest graph such that the initial state is a vertex and:

 * if `p` is a vertex and,
 * a transition `t` allows to reach a state `s` from `p` with action `a`

then `s` is also a vertex and there is an edge from `p` to `s` labelled by `(t,a)`.

## Using `hyena`

`hyena` consists of a library to model, extend, and simulate HyENAs, complemented with command line tools.

### Concrete syntax for models

Systems can be built fully in Python by instantiating classes, but usually it is more convenient to load them from files.
A system in `hyena` consists of three components:

 * a model that defines the classes to be used, eg, the basic model presented so far is defined in module `hyena.ena` (not shown here)
 * a Python file that defines defaults to instantiate these classes, that is, a template
 * a JSON file that defines the instances and may override these defaults 

The Python file `examples/simple.py` to build our simple example above is as follows:

```python
from hyena import Template

class Transition(Template):
    def action(self):
        idx = node.inputs[0].node
        if node.current == system.nodes[idx].current:
            return 0
        else:
            return 1
```

First it imports base class `Template` from `hyena`.
Then it defines a template for class `Transition` by sublassing `Template` and setting defaults for its field `.action`.
This means that every `Transition` instance to be created will be initialized this way unless otherwise specified.
We implement actions as a method of class `Transition`.
Since this method is defined in the scope of `Transition`, it has access to global objects `node` and `system` (as well as `transition` and `location` that are not used here) that will be provided at run time.
But currently these objects are undefined.
Thus, when using a Python type checker or linter while writing the template above, it may complain that `node` and `system` are not defined.
This can be fixed by adding two lines at the beginning of the template:

```python
from hyena import ena
system = ena.System.dummy()
node = ena.System.dummy()
```

The two objects are now declared and initialized consistently with dummy data.
In general, every name that is expected to exist at runtime only and is used inside a `Template` method can be declared this way: `system`, `node`, `location`, `transition`, and `input`.

Moreover, every name that is visible within the template file will be visible from the functions defined here.
For instance, if we add a global declaration `spam = 42` in `examples/simple.py` then method `Transition.cost` could refer to it.

Then, the JSON file `examples/simple.json` defines the full system as a nest of objects or arrays corresponding to the nesting of Python objects or arrays. 
In the code below, we add Python comments to the JSON source in order to make it clearer, but remember that JSON does not accept comments:

```python
{ # fields for system, that is: just .nodes
  "nodes": [ # system.nodes
    { # system.nodes[0]
      "inputs": [ # system.nodes[0].inputs
        { # system.nodes[0].inputs[0]
          "node": 1
        }
      ],
      "locations": [ # system.nodes[0].locations
        { # system.nodes[0].locations[0]
          "transitions": [ # system.nodes[0].locations[0].transitions
            { # system.nodes[0].locations[0].transitions[0]
              # only field .target is provided
              "target": 1
              # the rest will come for Python template
            }
          ]
        },
        { # system.nodes[0].locations[1]
          "transitions": [{"target": 0}]
        }
      ],
      "current": 0  # this could have been defined in Python template
    },
    { # system.nodes[1]
      "inputs": [{"node": 0}],
      "locations": [{"transitions": [{"target": 1}]},
                    {"transitions": [{"target": 0}]}],
      "current": 0
    }
  ]
}
```

A system is loaded from its three components:

 * first the classes for the model are loaded from a Python module, like `hyena.ena`
 * then a JSON file is loaded to provide the content of the instances to be constructed, normally starting from `System`
 * if some field is not given in this JSON file, it is taken from the Python template
 * if the field is not given either in the Python template, this result in an error if the field is primitive, or a warning otherwise
 * if other fields are provided in the JSON file or in the Python template, they are included in the generated objects and considered as constant fields (and as before, if a field is defined at both places, its value from the JSON file is preferred)

### Aborts and jumps

If a `Transition.action` raises exception `hyena.Abort`, it cannot be executed, but the exception is silently discarded.
This is how `Transition.action`, or any function that is called from it, signals that a transition is not executable in the current context.
This is quite different from a guard that usually returns a Boolean, here an action has two outcomes:

 * return a value, in which case it can be executed, its updates are committed as a new state, and the returned value is recorded into the trace or the state graph
 * raise `Abort`, in which case the transition cannot be executed, and its updates are rolled back

`hyena` also provides a way to arbitrarily assign the current location of nodes during the execution of an action, regardless of the existing transitions.
This is implemented as an exception `Jump` that can be raised from actions.
Look at `examples/jump.py` for instance:

```python
from hyena import ena, Template, Jump

system = ena.System.dummy()
node = ena.Node.dummy()

class Transition(Template):
    def action(self):
        node.count += 1
        if node.count == 3:
            node.count = 0
            raise Jump(0, {0: 0, 1: 0})
        elif self.sameloc():
            return 0
        else:
            return node.count
    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current

class Node(Template):
    current = 0
    count = 0
```

This template is similar to `examples/counter-tpl.py` except that, when `node.count` is found to reach `3` in `Transition.action`, it is reset to `0` and exception `Jump` is raised.
`Jump` expects first the action to decorate the transition with (which replace the return value as there will be none), and a `dict` that associates to nodes identified by their index their new `.current`.
So here this jumps is like returning `0` but at the same time we force the nodes `0` and `1` to both jump to their locations `0`.

Note that this kind of actions allows executing transitions that do not exist in the automata, which is the reason why we call them _jumps_ and implement them using an exception to emphasize that it breaks the standard execution rule.
Note also that, like in the example above, assignments performed during the action before raising `Jump` are committed to the state.
Indeed, raising `Jump` is not an error but a way to specify that we want to break the automata semantics and perform direct jumps into new locations.

### Drawing models

`hyena` allows to draw a model or a fully instantiated system.
To do so, module `hena` provides a command-line interface.
For instance:

```shell
sh> python -m hyena draw hyena.ena.System
```
The above command asks `hyena` to load class `System` in module `heyna.ena` and to draw it as a graph representing its fields and the classes they may contain.
This is how we obtained the first picture at the beginning of this README.
Option `-o PATH` allows to save the picture to a specific path, otherwise a default path is constructed (here `hyena_ena_System.pdf`)

```shell
sh> python -m hyena draw hyena.ena.System examples/simple.py examples/simple.json
```

The above command asks `hyena` to load a full system as defined in class `hyena.ena.System`, using the templates in `examples/simple.py` and the objects content defined in `examples/simple.json`.
Here again, option `-o` allows choosing output file.
Additionally, option `-g` allows passing [GraphViz](https://www.graphviz.org) options to be inserted at graph level, and option `-c` allows passing GraphViz options to be inserted at cluster level (ie, withing each node that contains an automaton).
Finally, option `-a` orders `hyena` to draw the automata inside each node, instead of just their current location.
For instance, the second picture above was generated using:

```shell
sh> python -m hyena draw -a -g "newrank=true; rankdir=LR" -c "rank=same" hyena.ena.System examples/simple.py examples/simple.json
```

### Simulation

`hyena` allows to simulate a system in several ways:

 * directly from Python using an instance of class `System`
 * through an interactive simulator that provides a basic user interface
 * by computing the reachable states and possibly checking them

#### Direct simulation from Python

From Python, one can load the module that defines the classes and then load a system for its Python and JSON files:

```ipython
In [1]: from hyena.ena import System

In [2]: system = System.from_json("examples/simple.json", "examples/simple.py")
```

This system object has exactly the expected fields and nested structures as described in the class graph (plus the extra fields that may have been provided in the JSON file or the Python template).
It also has a property `state` that returns the current state, and a method `succ()` that computes the successor states.

```ipython
In [3]: system.state
Out[3]: system[nodes=(node[current=0], node[current=0])]

In [4]: succ = list(system.succ())

In [5]: succ
Out[5]: 
[(system[nodes=(node[current=1], node[current=0])],
  ('nodes', 0, 'locations', 0, 'transitions', 0),
  0),
 (system[nodes=(node[current=0], node[current=1])],
  ('nodes', 1, 'locations', 0, 'transitions', 0),
  0)]
```

Note that `system.succ()` returns a generator (thus the use of `list` to capture its items) of triples `(s, p, a)` where:

 * each `s` is a successor state
 * each `p` is the path to the transition that was executed to reach `s` (one can use `system[p]` to retrieve the corresponding `Transition` instance)
 * each `a` is the value returned by the executed `Transition.action`

`system.state` can also be assigned to move to another state from which others successor states can be computed:

```ipython
In [6]: s, p, a = succ[0]

In [7]: system.state = s

In [8]: list(system.succ())
Out[8]: 
[(system[nodes=(node[current=0], node[current=0])],
  ('nodes', 0, 'locations', 1, 'transitions', 0),
  1),
 (system[nodes=(node[current=1], node[current=1])],
  ('nodes', 1, 'locations', 0, 'transitions', 0),
  1)]
```

It is also possible to pass directly a state to `system.succ()`:

```ipython
In [9]: s, p, a = succ[1]

In [10]: list(system.succ(s))
Out[10]: 
[(system[nodes=(node[current=0], node[current=1])],
  ('node', 0, 'locations', 1, 'transitions', 0),
  1),
 (system[nodes=(node[current=1], node[current=0])],
  ('node', 1, 'locations', 1, 'transitions', 0),
  1)]
```

#### Interactive simulation

Interactive simulation can be started with, eg:

```shell
sh> python -m hyena simul -j examples/simple.json -p examples/simple.py
```

This yields a shell that prompts for commands to explore a trace.
Option `-c` allows to load the system from a class other that `hyena.ena.System`.
Within the simulator, command `help` prints help about the available commands, and `help cmd` prints more details about a specific command.
States are displayed as trees rooted at `system`, and successor states are displayed as just what will change in the state.

#### Reachability analysis

Some models may reach finitely many states, for instance our simple model, because it has no variables other that the current location of its automata.
In such a case, `hyena` allows to compute all these reachable states and to check assertions on them.
However, if the set of reachable states is not finite, this computation will run until it crashes saturating the memory.
In such situations, an option is available to bound exploration to a finite number of states.

Reachability analyzer can be started with, eg:

```shell
sh> python -m hyena reach -j examples/simple.json -p examples/simple.py
```

Invoked this way, it will just explore the state-space until all reachable states are computed.
Like for `hyena simul`, option `-c` allows to load the system from a class other that `hyena.ena.System`.
Other options allow controlling exploration:

 * `-v` toggles printing each explored state
 * `-l NUM` limits the state-space exploration to `NUM` states
 * `-s PATH` saves the state-space to a JSON file after its exploration
 * `-a EXPR` adds an assertion to be checked on every state, see below
 * `-t` when an assertion is violated, prints a trace to it from initial state

Option `-a` adds a property to be checked on every state just before its successors are computed.
Using `-a` several times allow to check several properties.
For instance, one could run:

```shell
sh> python -m hyena reach -j examples/simple.json -p examples/simple.py -t -a 'system.nodes[0].current == 0'
assert failed 'system.nodes[0].current == 0'
#0 system[nodes=(node[current=0], node[current=0])]
>> system.nodes[0].locations[0].transitions[0] => 0
#1 system[nodes=(node[current=1], node[current=0])]
```

As shown above, assertions are Python Boolean expressions that check the values of some fields in a state.
Note that assertions are checked against the whole system, including the constant fields.
Note also that assertions may fail for two reasons: if they are not verified at a state, or if they raised an exception, in which case the error will be printed as well.

## Extending HyENAs

### Adding extra fields

The simplest method to extend a HyENA model is to add fields to it, either through a Python template or through the JSON file.
Consider for instance our previous example and assume that we want to simplify the expression of the actions by using an auxiliary function `sameloc()` to tell whether the two nodes are in the same current location.
This requires a function `sameloc()` to be visible in the scope of the actions.
We can achieve this by redefining the Python template and adding `sameloc` as a new method in `Transition` as follows (see also `examples/simple-bis.py`):

```python
from hyena import Template

class Transition(Template):
    cost = 42
    def action(self):
        if self.sameloc():
            return 0
        else:
            return self.cost
    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current
```

Note that such auxiliary functions may have additional parameters just like any method.
At any point of the objects hierarchy, we could include new names, storing values or functions, that will be made available as constant fields of the class where they have been defined.
For instance above we added to `Transition` a field `.cost` whose value is `42` and that is used from `.action`.

### Extending classes

The extension presented above does not change the HyENA classes, and it introduces only constants and intermediate methods that help writing a HyENA in a simpler way.
However, it is also possible to extend existing classes (or even to create completely new ones).
For instance, consider we want to add a counter to nodes in order to record how many transitions each node fired.
Then, we would like that the cost of a transition is either `0` as before, or is the value of this counter.
This cannot be made by just adding a class field as above because `hyena` would not consider it as part of the state.
To achieve this correctly, we must declare a new mutable field in class `None`, as in `examples/counter.py`:

```python
from hyena import ena, Annotated, F
from hyena.ena import *

@dataclass
class Node(ena.Node):
    count: Annotated[int, F.MUTABLE()]

@dataclass
class System(ena.System):
    pass
```

In this module, we import from `hyena` the submodule `ena` that we want to extend
Then we import everything from `hyena.ena` in order to make visible its classes.
Next, we extend class `Node` by adding a field `count` that is an `int` (doing so, we hide the previous value of `Node` that was imported from `hyena.ena`).
This field is declared mutable, see below for details, otherwise it would be a constant field.
Finally, we extend class `System`, but we add noting to it.
This step is required because later we will load systems from `examples.counter.System` and doing so, the library will query its module.
If we don't redefine `System`, the library would retrieve the value imported from `hyena.ena` which is not the extended version we want to use.
By redefining `System` this way, we ensure that the library is aware that the right module to work with is `examples.counter`.

To instantiate this model, we can reuse `examples/simple.json` as its JSON file, and use `examples/counter-tpl.py` as its Python template:

```python
from hyena import Template
from . import counter as xena

# to silent typecheckers
system = xena.System.dummy()
node = xena.Node.dummy()

class Transition(Template):
    def action(self):
        node.count += 1
        if self.sameloc():
            return 0
        else:
            return node.count
    def sameloc(self):
        idx = node.inputs[0].node
        return node.current == system.nodes[idx].current

class Node(Template):
    current = 0
    count = 0
```

This template defines the default values for:

 * `Transition.action` and `Transition.sameloc`, adapted from the one we had previously
 * `Node.current` (which will be overridden from JSON because so does `examples/simple.json`)
 * `Node.count` that is zero initially

#### `Struct` and fields

Every class defined in an extension module like above should be either a subclass of one from basic HyENAs, or a subclass of `hyena.Struct` (that itself is the parent class of HyENAs classes).
`hyena` also provides `hyena.StrEnum` that is a recognized extension of standard `enum.StrEnum` (in particular, it is drawn in class diagrams).
Any other class or object defined in an extension module may not work as expected as `hyena` will not consider it when constructing the scopes of methods.
On the other hand, anything declared within a Python template will be visible at run time.

The fields of a `Struct` subclass should be all declared _without_ a default value (this is templates' job to do this) and with a type hint that `hyena` understands, that is either a basic Python type hint `hint`, `Annotated[hint, ...]` to add further information needed by `hyena`.
Basic hints include:

 * `hint` can basically be one of `bool`, `int`, a subclass of `Struct`, or an instance of `StrEnum`
 * `Callable` is the type hint for a method or auxiliary function, for instance this is the type of `Transition.action`
 * `Callable[[], type]` is a more detailed type hint that specifies the return type, this information is not used, but it is displayed in the class diagram as `(type)`
 * `list[base]` is an array storing instances of type `base`
 * `Optional[base]` is an optional field, if it is not given in the JSON file nor in the template, its value is initialized to `None`

Further information may be passed to `hyena` using `Annotated` type hints, and a helper class `hyena.F`:

 * `Annotated[int, F.INDEX(array)]` is an `int`-valued field that ranges over the index of the given array (passed as a string), for instance:
   - `Node.current` has type hint `Annotated[int, F.INDEX(".location")]`
   - `Input.node` has type hint `Annotated[int, F.INDEX("Node.nodes")]`
 * `Annotated[list[base], F.INDEX(size)]` is an array that contains values described by `base` and whose size is constrained by field `size` itself given as a string that is either:
   - the name of an `int`-valued field as above (`".name"` to refer to a field in the current class, or `"Class.name"` to refer to a field in another class)
   - or as the index in another array (eg, `#.name` or `#Class.name`) which means that both arrays have the same size
 * `Annotated[hint, F.MUTABLE()]` defines a mutable field, if `F.MUTABLE()` is not used then the field is non-mutable
 * `Annotated[hint, F.UNIQUE(scope)]` is a field whose value is expected to be unique in the given `scope`, the latter being the name of a `Struct` subclass. For instance:
   - defining a field `Node.name: Annotated[str, F.UNIQUE("System")]` states that every `Node` instance should have a value in its field `.name` that is distinct from that in every other node
   - defining a field `Location.name: Annotated[str, F.UNIQUE("Node")]` is similar but distinct nodes may have locations with the same `.name` as the scope is here limited to `Node`
 * `Annotated[base, F.MACRO(expr)]` defines a constant field whose value has type `base` and will be computed from `expr` when the `System` is instantiated (ie, at the initial state), for instance, considering we have added `Node.name` as above, we could add `Input.name: Annotated[str, F.MACRO("system.nodes[input.node].name)"]` thus the name of an input is the name of the node it corresponds to

Several annotations may be combined with a `|`, for instance, `Annotated[int, F.INDEX(...) | F.MUTABLE()]` is a valuated mutable `int`-field whose range is constrained.
Not all these typing constraints are currently enforced at runtime, but future version of `hyena` will progressively do it.

## Installation

Within the project directory cloned from the [`git` repository](https://github.com/fpom/hyena/), run:

```shell
sh> pip install .
```

This will install `hyena` and its dependencies:

 * [`colorama`](https://github.com/tartley/colorama)
 * [`typer`](https://typer.tiangolo.com)
 * [`rich`](https://github.com/Textualize/rich)
 * [`frozendict`](https://github.com/Marco-Sulla/python-frozendict)

Dependency to `colorama` is a legacy from the first versions and it will be replaced with `rich`.

## Licence

`hyena` is (C) 2023 Franck Pommereau <franck.pommereau@univ-evry.fr> and released under the terms of the MIT licence, see `LICENCE.md`.

This work was supported by the French government as part of the _France 2030_ program, within the framework of the SystemX Technological Research Institute.
