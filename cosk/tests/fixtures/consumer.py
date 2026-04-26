from wrappers import wrapper


def consume(dep=wrapper()) -> str:
    """Consume wrapped output."""
    return dep
