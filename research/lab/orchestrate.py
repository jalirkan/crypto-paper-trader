"""The search loop and the sealed holdout.

Data discipline:
- `SearchLab` is constructed with the SEARCH span only — it cannot touch
  holdout bars because it never receives them.
- `finalize()` is the only function that sees the holdout, evaluates only the
  top-M survivors, exactly once, and judges them with DSR (N = every trial
  ever recorded in lab.db) and a stationary-bootstrap p-value vs buy-and-hold.

Every evaluated candidate is persisted; trials accumulate across runs and
generators — the statistics never forget what was tried.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from ..backtest import engine
from . import dsl, interpret, stats

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LAB_DB = ROOT / "data" / "lab.db"
FEE_BPS, SLIP_BPS = 10.0, 5.0

LAB_SCHEMA = """
CREATE TABLE IF NOT EXISTS lab_candidates (
  hash        TEXT PRIMARY KEY,
  canonical   TEXT NOT NULL,
  source      TEXT NOT NULL,          -- random | claude
  generation  INTEGER NOT NULL,
  ts          INTEGER NOT NULL,
  train_sharpe REAL,                  -- per-bar
  robust_sharpe REAL,
  train_stats TEXT
);
CREATE TABLE IF NOT EXISTS lab_finals (
  hash        TEXT PRIMARY KEY,
  ts          INTEGER NOT NULL,
  holdout_stats TEXT NOT NULL
);
"""


def lab_db(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DEFAULT_LAB_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(LAB_SCHEMA)
    return conn


class SearchLab:
    def __init__(self, search_closes: list[float], conn: sqlite3.Connection, source: str):
        self.closes = list(search_closes)  # search span ONLY
        self.conn = conn
        self.source = source

    def evaluate(self, candidate: dict, generation: int) -> dict | None:
        """Validate → dedupe → score on the search span. None if dupe/invalid."""
        try:
            dsl.validate(candidate)
        except dsl.DslError:
            return None
        h = dsl.cand_hash(candidate)
        if self.conn.execute(
            "SELECT 1 FROM lab_candidates WHERE hash=?", (h,)
        ).fetchone():
            return None

        w = interpret.weights(candidate, self.closes)
        res = engine.run(self.closes, w, FEE_BPS, SLIP_BPS)
        train_sharpe = stats.sharpe_per_bar(res.returns)

        # Robustness: worst neighbor when each window param wiggles ±25%.
        neighbor_sharpes = []
        for node, n in dsl.window_params(candidate):
            for factor in (0.75, 1.25):
                n2 = max(dsl.N_MIN, min(dsl.N_MAX, int(n * factor)))
                if n2 == n:
                    continue
                node["n"] = n2
                w2 = interpret.weights(candidate, self.closes)
                neighbor_sharpes.append(
                    stats.sharpe_per_bar(engine.run(self.closes, w2, FEE_BPS, SLIP_BPS).returns)
                )
                node["n"] = n
        robust = min([train_sharpe, *neighbor_sharpes]) if neighbor_sharpes else train_sharpe

        # Degenerate filters: must actually trade, and not churn itself to death.
        s = res.stats
        if s.get("trades", 0) < 4 or s.get("exposure", 0) < 0.02:
            robust = -abs(robust) - 1.0  # bury do-nothing candidates

        self.conn.execute(
            "INSERT INTO lab_candidates VALUES (?,?,?,?,?,?,?,?)",
            (
                h,
                dsl.canonical(candidate),
                self.source,
                generation,
                int(time.time() * 1000),
                train_sharpe,
                robust,
                json.dumps(s),
            ),
        )
        self.conn.commit()
        return {"hash": h, "train_sharpe": train_sharpe, "robust": robust, "stats": s}

    def elites(self, k: int = 6) -> list[dict]:
        rows = self.conn.execute(
            "SELECT canonical FROM lab_candidates ORDER BY robust_sharpe DESC LIMIT ?",
            (k,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def history_summary(self, k: int = 30) -> str:
        rows = self.conn.execute(
            """SELECT canonical, train_sharpe, robust_sharpe FROM lab_candidates
               ORDER BY robust_sharpe DESC LIMIT ?""",
            (k,),
        ).fetchall()
        return "\n".join(
            f"SR {r[1]:+.4f} (robust {r[2]:+.4f}): {r[0]}" for r in rows
        )

    def run_generations(self, generator, generations: int, pop: int, log=print) -> None:
        for g in range(generations):
            proposals = generator.propose(pop, self.elites())
            evaluated = 0
            best = None
            for cand in proposals:
                out = self.evaluate(cand, g)
                if out is None:
                    continue
                evaluated += 1
                if best is None or out["robust"] > best["robust"]:
                    best = out
            total = self.conn.execute("SELECT COUNT(*) FROM lab_candidates").fetchone()[0]
            log(
                f"gen {g}: evaluated {evaluated}/{len(proposals)} "
                f"(total trials {total}) best robust SR "
                f"{best['robust']:+.4f}" if best else f"gen {g}: nothing evaluable"
            )


def finalize(
    full_closes: list[float],
    search_len: int,
    conn: sqlite3.Connection,
    top_m: int = 3,
) -> dict:
    """The one and only holdout evaluation. Judgement day for the top-M."""
    n_trials = conn.execute("SELECT COUNT(*) FROM lab_candidates").fetchone()[0]
    trial_sharpes = [
        r[0]
        for r in conn.execute(
            "SELECT train_sharpe FROM lab_candidates WHERE train_sharpe IS NOT NULL"
        )
    ]
    finalists = conn.execute(
        """SELECT hash, canonical, train_sharpe, robust_sharpe FROM lab_candidates
           ORDER BY robust_sharpe DESC LIMIT ?""",
        (top_m,),
    ).fetchall()

    # Holdout returns: weights computed on the full series (warm-up runs into
    # the search span, which is fine — it's the RETURNS after the boundary
    # that were never seen during search).
    boundary = search_len
    bh = engine.buy_and_hold(full_closes[boundary - 1 :], FEE_BPS, SLIP_BPS)

    results = []
    for h, canon, tr_sr, rob_sr in finalists:
        cand = json.loads(canon)
        w = interpret.weights(cand, full_closes)
        res = engine.run(full_closes[boundary - 1 :], w[boundary - 1 :], FEE_BPS, SLIP_BPS)
        excess = [a - b for a, b in zip(res.returns, bh.returns)]
        dsr = stats.deflated_sharpe(res.returns, n_trials, trial_sharpes)
        entry = {
            "hash": h,
            "candidate": cand,
            "train_sharpe": tr_sr,
            "robust_sharpe": rob_sr,
            "holdout": res.stats,
            "holdout_vs_bh_pvalue": stats.stationary_bootstrap_pvalue(excess),
            "dsr": dsr,
            "verdict": "PASS"
            if dsr["dsr"] >= 0.95 and stats.stationary_bootstrap_pvalue(excess) <= 0.05
            else "FAIL",
        }
        results.append(entry)
        conn.execute(
            "INSERT OR REPLACE INTO lab_finals VALUES (?,?,?)",
            (h, int(time.time() * 1000), json.dumps(entry, default=str)),
        )
    conn.commit()
    return {
        "n_trials": n_trials,
        "holdout_bars": len(full_closes) - boundary,
        "benchmark": bh.stats,
        "finalists": results,
    }
