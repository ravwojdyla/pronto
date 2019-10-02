import collections
import inspect
import itertools
import functools
import types
import typing
from typing import Callable, ClassVar, Optional, Union, Tuple


T = typing.TypeVar('T')
F = typing.TypeVar('F', bound=Callable[..., object])


class typechecked(object):

    @classmethod
    def check_type(cls, hint: object, value: object) -> Tuple[bool, Optional[str]]:
        # None: check if None
        if hint is None.__class__:
            return (value is None, "None")
        # direct type annotation: simply do an instance check
        if isinstance(hint, type):
            return (isinstance(value, hint), hint.__name__)
        # typing.Any is always true
        if getattr(hint, '_name', None) == 'typing.Any':
            return (True, None)
        # typing.Set needs to check member types
        if getattr(hint, '__origin__', None) is set:
            if not isinstance(value, collections.abc.MutableSet):
                return (False, f"set of { hint.__args__ }")
            for arg in value:
                if not cls.check_type(hint.__args__, value):
                    return (False, f"set of { hint.__args__ }")
        # typing.FrozenSet needs to check member types
        if getattr(hint, '__origin__', None) is frozenset:
            if not isinstance(value, collections.abc.Set):
                return (False, f"frozen set of { hint.__args__ }")
            for arg in value:
                if not cls.check_type(hint.__args__, value):
                    return (False, f"frozen set of { hint.__args__ }")
        # typing.Union needs to be a valid type
        if getattr(hint, '__origin__', None) == typing.Union:
            results = {}
            for arg in hint.__args__:
                results[arg] = cls.check_type(arg, value)
            ok = any(ok for ok,name in results.values())
            return (ok, ", ".join(name for ok,name in results.values()))
        return (False, "something")

    def __init__(self, property: bool = False) -> None:
        self.property = property

    def __call__(self, func: F) -> F:
        if not __debug__:
            return func

        hints = typing.get_type_hints(func)

        @functools.wraps(func)
        def newfunc(*args, **kwargs):
            callargs = inspect.getcallargs(func, *args, **kwargs)
            for name, value in callargs.items():
                if name in hints:
                    well_typed, type_name = self.check_type(hints[name], value)
                    if not well_typed:
                        msg = f"'{{}}' must be {type_name}, not {type(value).__name__}"
                        if self.property:
                            raise TypeError(msg.format(func.__name__))
                        else:
                            raise TypeError(msg.format(name))
            return func(*args, **kwargs)

        return newfunc


class roundrepr(object):
    """A class-decorator to build a minimal `__repr__` method that roundtrips.
    """

    @staticmethod
    def make(class_name: str, *args, **kwargs):
        """Generate a repr string.

        Positional arguments should be the positional arguments used to
        construct the class. Keyword arguments should consist of tuples of
        the attribute value and default. If the value is the default, then
        it won't be rendered in the output.

        Example:
            >>> from pronto.utils.meta import roundrepr
            >>> class MyClass(object):
            ...     def __init__(self, name=None):
            ...         self.name = name
            ...     def __repr__(self):
            ...         return roundrepr.make('MyClass', 'foo', name=(self.name, None))
            >>> MyClass('Will')
            MyClass('foo', name='Will')
            >>> MyClass(None)
            MyClass('foo')

        Credits:
            `PyFilesystem2 <https://github.com/PyFilesystem/pyfilesystem2/blob/master/fs/_repr.py>`_
            code developed by `Will McGugan <https://github.com/willmcgugan>`_.
        """
        arguments = [repr(arg) for arg in args]
        arguments.extend(
            [
                "{}={!r}".format(name, value)
                for name, (value, default) in sorted(kwargs.items())
                if value != default and value
            ]
        )
        return "{}({})".format(class_name, ", ".join(arguments))

    def __new__(self, cls: T) -> T:
        obj = super().__new__(self)
        obj.__init__()
        if isinstance(cls, type):
            return obj(cls)
        return obj

    def __call__(self, cls: T) -> T:

        # Extract signature of `__init__`
        sig = inspect.signature(cls.__init__)
        if not all(p.kind is p.POSITIONAL_OR_KEYWORD for p in sig.parameters.values()):
            raise TypeError("cannot use `roundrepr` on a class with variadic `__init__`")

        # Derive the __repr__ implementation
        def __repr__(self_):
            args, kwargs = [], {}
            for name, param in itertools.islice(sig.parameters.items(), 1, None):
                if param.default is inspect.Parameter.empty:
                    args.append(getattr(self_, name))
                else:
                    kwargs[name] = (getattr(self_, name), param.default)
            return self.make(cls.__name__, *args, **kwargs)

        # Hotpatch the class and return it
        cls.__repr__ = __repr__
        return cls