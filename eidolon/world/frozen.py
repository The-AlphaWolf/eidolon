"""`FrozenDict` — an immutable mapping for the sealed case (I-4).

`Case` and every model reachable from it are `ConfigDict(frozen=True)`, but pydantic's
`frozen` only blocks attribute REBINDING. A `dict`-typed field is still a live, mutable
container: `case.actors["Ghost"] = ...` succeeded on a sealed case and changed its
`content_hash()` — I-4 ("canonical case data is immutable after validation") held for the
attributes and not for what they pointed at.

A `dict` subclass rather than `types.MappingProxyType`: the proxy is not JSON-serializable
by pydantic (`PydanticSerializationError: unknown type mappingproxy`), and the case has to
round-trip through `model_dump_json`/`model_validate_json` unchanged. A dict subclass
serializes, compares and reads exactly like the dict it replaces, so no call site changes.
"""
from __future__ import annotations

import copy
from typing import Annotated, TypeVar

from pydantic import AfterValidator

K = TypeVar("K")
V = TypeVar("V")


class FrozenDict(dict):
    """A `dict` whose every mutating operation raises. Reads, iteration, `==`, `len`,
    `dict(...)` and JSON serialization are unchanged."""

    __slots__ = ()

    def _immutable(self, *_args, **_kwargs):
        raise TypeError(f"{type(self).__name__} is immutable (I-4: sealed case data)")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    update = _immutable
    setdefault = _immutable
    pop = _immutable
    popitem = _immutable
    clear = _immutable

    # `dict.__reduce__` would round-trip through `__setitem__`; give copy/pickle a
    # constructor call instead (pydantic's `model_copy(deep=True)` deep-copies fields).
    def __reduce__(self):
        return (type(self), (dict(self),))

    def __copy__(self) -> "FrozenDict":
        return type(self)(self)

    def __deepcopy__(self, memo) -> "FrozenDict":
        return type(self)({k: copy.deepcopy(v, memo) for k, v in self.items()})


def _freeze(d: dict) -> FrozenDict:
    return FrozenDict(d)


Frozen = Annotated[dict[K, V], AfterValidator(_freeze)]
"""Use as `Frozen[KeyType, ValueType]` on any field of the sealed case."""
