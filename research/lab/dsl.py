"""Strategy DSL — JSON expression trees. No code execution, ever.

A candidate is:
    {"entry": <bool-expr>, "exit": <bool-expr>}

Series expressions (all trailing-window, defined in interpret.py):
    {"op": "close"}
    {"op": "sma"|"ema"|"roll_max"|"roll_min"|"vol"|"ret"|"rsi", "n": int, "of": <series>}
    {"op": "const", "v": number}          # broadcast scalar (thresholds)

Boolean expressions:
    {"op": "gt"|"lt", "a": <series>, "b": <series>}
    {"op": "cross_above"|"cross_below", "a": <series>, "b": <series>}
    {"op": "and"|"or", "a": <bool>, "b": <bool>}
    {"op": "not", "a": <bool>}

Bounds keep the search space sane and the interpreter O(nodes × bars).
"""

from __future__ import annotations

import hashlib
import json

SERIES_OPS = {"close", "sma", "ema", "roll_max", "roll_min", "vol", "ret", "rsi", "const"}
WINDOW_OPS = {"sma", "ema", "roll_max", "roll_min", "vol", "ret", "rsi"}
CMP_OPS = {"gt", "lt", "cross_above", "cross_below"}
LOGIC_OPS = {"and", "or", "not"}

MAX_NODES = 25
MAX_DEPTH = 7
N_MIN, N_MAX = 2, 200
CONST_MIN, CONST_MAX = -1.0, 100.0  # thresholds: RSI 0-100, returns/vol as fractions


class DslError(ValueError):
    pass


def _walk_series(node, depth: int) -> int:
    if depth > MAX_DEPTH:
        raise DslError("max depth exceeded")
    if not isinstance(node, dict) or "op" not in node:
        raise DslError(f"malformed node: {node!r}")
    op = node["op"]
    if op not in SERIES_OPS:
        raise DslError(f"unknown series op: {op}")
    if op == "close":
        return 1
    if op == "const":
        v = node.get("v")
        if not isinstance(v, (int, float)) or not (CONST_MIN <= v <= CONST_MAX):
            raise DslError(f"const out of bounds: {v!r}")
        return 1
    # window ops
    n = node.get("n")
    if not isinstance(n, int) or not (N_MIN <= n <= N_MAX):
        raise DslError(f"{op}: n out of bounds: {n!r}")
    return 1 + _walk_series(node.get("of", {"op": "close"}), depth + 1)


def _walk_bool(node, depth: int) -> int:
    if depth > MAX_DEPTH:
        raise DslError("max depth exceeded")
    if not isinstance(node, dict) or "op" not in node:
        raise DslError(f"malformed node: {node!r}")
    op = node["op"]
    if op in CMP_OPS:
        return 1 + _walk_series(node["a"], depth + 1) + _walk_series(node["b"], depth + 1)
    if op == "not":
        return 1 + _walk_bool(node["a"], depth + 1)
    if op in LOGIC_OPS:
        return 1 + _walk_bool(node["a"], depth + 1) + _walk_bool(node["b"], depth + 1)
    raise DslError(f"unknown bool op: {op}")


def validate(candidate: dict) -> None:
    """Raises DslError unless the candidate is well-formed and within bounds."""
    if not isinstance(candidate, dict):
        raise DslError("candidate must be an object")
    for key in ("entry", "exit"):
        if key not in candidate:
            raise DslError(f"missing {key}")
    nodes = _walk_bool(candidate["entry"], 1) + _walk_bool(candidate["exit"], 1)
    if nodes > MAX_NODES:
        raise DslError(f"too many nodes: {nodes} > {MAX_NODES}")


def _strip(node):
    """Keep only grammar keys, recursively, with deterministic ordering."""
    if not isinstance(node, dict):
        return node
    out = {}
    for k in sorted(node):
        if k in ("op", "n", "v", "a", "b", "of", "entry", "exit"):
            v = node[k]
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            out[k] = _strip(v) if isinstance(v, dict) else v
    return out


def canonical(candidate: dict) -> str:
    return json.dumps(
        {"entry": _strip(candidate["entry"]), "exit": _strip(candidate["exit"])},
        sort_keys=True,
        separators=(",", ":"),
    )


def cand_hash(candidate: dict) -> str:
    return hashlib.sha256(canonical(candidate).encode()).hexdigest()[:16]


def window_params(candidate: dict) -> list[tuple[dict, int]]:
    """All (node, n) pairs — used for robustness neighbors and mutation."""
    found: list[tuple[dict, int]] = []

    def rec(node):
        if isinstance(node, dict):
            if node.get("op") in WINDOW_OPS and isinstance(node.get("n"), int):
                found.append((node, node["n"]))
            for k in ("a", "b", "of", "entry", "exit"):
                if k in node:
                    rec(node[k])

    rec(candidate)
    return found
