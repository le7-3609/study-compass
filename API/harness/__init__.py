"""Hand-written agent harness on the raw Messages API. One file per responsibility."""
from pathlib import Path

QUIET = False


def logger(file: str):
    """Every runtime action is printed with the name of the file that performed it."""
    name = Path(file).name

    def log(msg: str) -> None:
        if not QUIET:
            print(f"  [{name}] {msg}")
    return log
