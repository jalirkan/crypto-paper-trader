"""Candidate generators: seeded random search (baseline) and Claude-guided.

The random generator doubles as a scientific control — if Claude-guided
search can't beat random search per trial, that's a finding worth publishing.
"""

from __future__ import annotations

import json
import os
import random
import re
import urllib.request

from . import dsl

WINDOWS = [5, 10, 14, 20, 30, 40, 55, 80, 100, 150, 200]


class RandomGenerator:
    """Template-based random candidates + mutation of survivors."""

    def __init__(self, seed: int = 1):
        self.rng = random.Random(seed)

    def _series(self, depth=0) -> dict:
        r = self.rng
        n = r.choice(WINDOWS)
        op = r.choice(["sma", "ema", "roll_max", "roll_min", "ret", "vol"])
        if depth == 0 and r.random() < 0.25:
            return {"op": op, "n": n, "of": self._series(depth + 1)}
        return {"op": op, "n": n, "of": {"op": "close"}}

    def _bool(self) -> dict:
        r = self.rng
        kind = r.random()
        if kind < 0.35:  # breakout / breakdown
            op = r.choice(["cross_above", "cross_below", "gt", "lt"])
            return {"op": op, "a": {"op": "close"}, "b": self._series()}
        if kind < 0.6:  # two-series relation (trend)
            op = r.choice(["cross_above", "cross_below", "gt", "lt"])
            return {"op": op, "a": self._series(), "b": self._series()}
        if kind < 0.85:  # rsi threshold
            thr = r.choice([20, 25, 30, 40, 50, 60, 70, 75, 80])
            return {
                "op": r.choice(["gt", "lt"]),
                "a": {"op": "rsi", "n": r.choice([7, 14, 21, 30]), "of": {"op": "close"}},
                "b": {"op": "const", "v": thr},
            }
        # momentum sign
        return {
            "op": r.choice(["gt", "lt"]),
            "a": {"op": "ret", "n": r.choice(WINDOWS), "of": {"op": "close"}},
            "b": {"op": "const", "v": 0},
        }

    def fresh(self) -> dict:
        cand = {"entry": self._bool(), "exit": self._bool()}
        if self.rng.random() < 0.3:
            cand["entry"] = {"op": "and", "a": cand["entry"], "b": self._bool()}
        return cand

    def mutate(self, cand: dict) -> dict:
        c = json.loads(dsl.canonical(cand))
        params = dsl.window_params(c)
        r = self.rng
        choice = r.random()
        if params and choice < 0.5:  # wiggle a window
            node, n = r.choice(params)
            node["n"] = max(dsl.N_MIN, min(dsl.N_MAX, int(n * r.choice([0.7, 0.8, 1.25, 1.5])) or n + 1))
        elif choice < 0.75:  # regenerate exit
            c["exit"] = self._bool()
        else:  # regenerate entry
            c["entry"] = self._bool()
        return c

    def propose(self, k: int, elites: list[dict]) -> list[dict]:
        out = []
        for i in range(k):
            if elites and i % 2 == 1:
                out.append(self.mutate(self.rng.choice(elites)))
            else:
                out.append(self.fresh())
        return out


GRAMMAR_DOC = """Series ops (all trailing-window, no look-ahead):
  {"op":"close"} | {"op":"const","v":num in [-1,100]}
  {"op":"sma"|"ema"|"roll_max"|"roll_min"|"vol"|"ret"|"rsi","n":int 2-200,"of":<series>}
  (roll_max/roll_min use the window strictly BEFORE the current bar)
Bool ops:
  {"op":"gt"|"lt"|"cross_above"|"cross_below","a":<series>,"b":<series>}
  {"op":"and"|"or","a":<bool>,"b":<bool>} | {"op":"not","a":<bool>}
Candidate: {"entry":<bool>,"exit":<bool>}  (long/flat state machine)
Limits: ≤25 nodes, depth ≤7."""


class ClaudeGenerator:
    """Asks Claude for candidates, conditioned on what already failed/worked."""

    def __init__(self, model: str | None = None):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required for --generator claude")
        self.model = model or os.environ.get("LAB_MODEL", "claude-sonnet-5")

    def propose(self, k: int, elites: list[dict], history: str = "") -> list[dict]:
        system = (
            "You are the hypothesis engine of a quantitative research lab searching "
            "for long/flat daily BTC strategies. Propose candidates in a strict JSON "
            f"DSL.\n\n{GRAMMAR_DOC}\n\n"
            "Principles: prefer economically-motivated hypotheses (trend persistence, "
            "breakout, volatility regimes, mean reversion) over arbitrary complexity; "
            "diversify across hypothesis families; avoid near-duplicates of listed "
            "failures. Respond with ONLY a JSON array of candidate objects."
        )
        user = (
            f"Evaluation history (canonical → train Sharpe):\n{history or '(none yet)'}\n\n"
            f"Current elites:\n{json.dumps(elites) if elites else '(none)'}\n\n"
            f"Propose {k} new, diverse candidates."
        )
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(
                {
                    "model": self.model,
                    "max_tokens": 4000,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                }
            ).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as res:
            data = json.loads(res.read().decode())
        text = next(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        start, end = cleaned.find("["), cleaned.rfind("]")
        items = json.loads(cleaned[start : end + 1])
        return [c for c in items if isinstance(c, dict)]
