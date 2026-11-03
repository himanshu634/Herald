"""Shared by the node log lines.

Each node logs one line keyed by email id, so runs of parallel emails can be told apart.
Only ids, enums, counts and timings: never the sender, subject, body or the model's free text.
"""

from collections.abc import Iterable


def names(items: Iterable[str]) -> str:
    return ",".join(sorted(items)) or "none"
