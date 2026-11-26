# Python Typing and Metaprogramming Reference

## 1. Modern Type System Idioms (Python 3.10–3.13)

### Structural Subtyping with `Protocol`
Prefer `Protocol` over abstract base classes when callers only need a behavioral contract:

```python
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

class Fetcher(Protocol):
    async def fetch(self, url: str, *, timeout: float = 5.0) -> bytes: ...

def process_batch(fetcher: Fetcher, urls: Sequence[str]) -> None:
    ...
```

- Accept **abstract, covariant** input types (`Sequence[T]`, `Mapping[K, V]`, `Iterable[T]`) and return **concrete** types (`list[T]`, `dict[K, V]`).
- `list[Animal]` is **invariant**: a `list[Dog]` cannot be passed to `list[Animal]` because mutating it could insert a `Cat`. Use `Sequence[Animal]` when read-only.

### Type-Safe Decorators with `ParamSpec` and `TypeVar`
```python
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def log_calls(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)
    return wrapper
```

### Discriminated Unions and Exhaustiveness Checking
```python
from dataclasses import dataclass
from typing import Literal, Never, assert_never

@dataclass(frozen=True, slots=True)
class Ok[T]:
    kind: Literal["ok"]
    value: T

@dataclass(frozen=True, slots=True)
class Err:
    kind: Literal["err"]
    message: str

Result = Ok[int] | Err

def handle(res: Result) -> int:
    match res:
        case Ok(value=v):
            return v
        case Err(message=msg):
            raise RuntimeError(msg)
        case _:
            assert_never(res)  # mypy/pyright fails if a new variant is unhandled
```

### `NewType` vs `TypeAlias`
- `type UserId = int` is an alias (interchangeable with `int`).
- `UserId = NewType("UserId", int)` prevents accidentally passing `OrderId` where `UserId` is expected, with zero runtime cost.

## 2. Data Model, Descriptors, and Memory Layout

### `__slots__` and Frozen Dataclasses
Every standard Python object allocates a per-instance `__dict__` (~104+ bytes overhead). `@dataclass(frozen=True, slots=True)`:
- Cuts per-instance memory by 40–60% for millions of records.
- Prevents accidental typo-attribute creation (`obj.naem = ...` raises `AttributeError`).
- Makes instances hashable and safe as dict keys / cache entries (when fields are hashable).
- **Gotcha:** `slots=True` disables weak references unless `weakref_slot=True` (3.11+) is set, and breaks multiple inheritance if two parent classes define non-empty `__slots__`.

### Descriptors (How `@property`, Methods, and ORMs Work)
A descriptor implements `__get__`, `__set__`, or `__delete__`.
- **Data descriptor** (defines `__set__` or `__delete__`): takes precedence over instance `__dict__`.
- **Non-data descriptor** (defines only `__get__`, e.g., regular methods, `functools.cached_property`): instance `__dict__` takes precedence, allowing one-time lazy computation caching.

```python
class PositiveFloat:
    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = f"_{name}"

    def __get__(self, obj: object, objtype: type | None = None) -> float:
        if obj is None:
            return self  # type: ignore[return-value]
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: float) -> None:
        if value <= 0:
            raise ValueError(f"{self._attr} must be > 0, got {value}")
        setattr(obj, self._attr, float(value))
```

### `__init_subclass__` Over Metaclasses
Use `__init_subclass__` for plugin registration, interface validation, and class-level hooks. Reserve custom metaclasses ONLY when you need to alter class creation namespace (`__prepare__`) or customize `isinstance`/`issubclass` or operator behavior on class objects themselves (e.g., `Enum`).

```python
class Parser:
    registry: dict[str, type["Parser"]] = {}

    def __init_subclass__(cls, *, media_type: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if media_type is not None:
            if media_type in cls.registry:
                raise ValueError(f"Duplicate parser for {media_type}")
            cls.registry[media_type] = cls
```

## 3. Clean Error & Context Manager Patterns

- Use `contextlib.ExitStack` / `AsyncExitStack` when acquiring a dynamic list of resources so cleanup is guaranteed in reverse order even if resource #3 fails to open.
- Never catch `Exception` inside a retry loop without excluding programming errors (`TypeError`, `KeyError`, `AttributeError`) or allowlisting transient errors (`TimeoutError`, `ConnectionError`, `OSError`).
- Preserve original tracebacks with `raise DomainError("context") from err`, or suppress noisy internal noise deliberately with `from None`.
