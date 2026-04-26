from helpers import helper


def wrapper(dep=helper()) -> str:
    """Wrap helper output."""
    return dep
