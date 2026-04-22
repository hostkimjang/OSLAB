def add(left: int, right: int) -> int:
    return left + right


def divide(left: int, right: int) -> float:
    if right == 0:
        raise ValueError("right must not be zero")
    return left / right


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split()).title()
