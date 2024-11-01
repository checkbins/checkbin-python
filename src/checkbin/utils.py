from typing import TypeVar, Type, TYPE_CHECKING

T = TypeVar("T")


def with_typehint(baseclass: Type[T]):
    """
    Add type hints from a specified class to a base class:

    >>> class Foo(with_typehint(Bar)):
    ...     pass

    This would add type hints from class ``Bar`` to class ``Foo``.
    """
    if TYPE_CHECKING:
        # In the case of type checking: pretend that the target class inherits
        # from the specified base class
        return baseclass

    # Otherwise: just inherit from `object` like a regular Python class
    return object
