from __future__ import annotations

import sys

from .runtime import MLXRuntime
from .service import run


def main() -> int:
    return run(sys.stdin, sys.stdout, MLXRuntime())


if __name__ == "__main__":
    raise SystemExit(main())
