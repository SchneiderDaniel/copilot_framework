from __future__ import annotations

import json
import sys


def write_json(payload: object) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def write_error(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.write("\n")

