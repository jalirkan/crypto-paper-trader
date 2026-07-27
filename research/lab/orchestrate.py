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
    def __init__(
        self,
        search_closes: list[float] | dict[str, list[float]],
        conn: sqlite3.Connection,
        source: str,
    ):
        # Single-asset (list) or multi-asset (dict). SEARCH spans only.
        if isinstance(search_closes, dict):
            self.closes_map = {k: list(v) for k, v in search_closes.items()}
        else:
            self.closes_map = {"_": list(search_closes)}
        self.closes = next(iter(self.closes_map.values()))  # back-compat
        self.conn = conn
        self.source = source

    def _score_on(self, candidate: dict, closes: list[float]) -> tuple[float, dict]:
        w = interpret.weights(candidate, closes)
        res = engine.run(closes, w, FEE_BPS, SLIP_BPS)
        return stats.sharpe_per_bar(res.returns), res.stats

    def evaluate(self, candidate: dict, generation: int) -> dict | None:
        """Validate → dedupe → score on the search span(s). None if dupe/invalid.

        Multi-asset scoring: train = MEAN Sharpe across assets, robust = MIN
        across assets of the worst ±25%-window-wiggle neighbor. A candidate
        must work everywhere, including under perturbation, to rank."""
        try:
            dsl.validate(candidate)
        except dsl.DslError:
            return None
        h = dsl.cand_hash(candidate)
        if self.conn.execute(
            "SELECT 1 FROM lab_candidates WHERE hash=?", (h,)
        ).fetchone():
            return None

        per_asset: dict[str, dict] = {}
        asset_robusts: list[float] = []
        asset_sharpes: list[float] = []
        for sym, closes in self.closes_map.items():
            sr, s = self._score_on(candidate, closes)
            neighbor_sharpes = []
            for node, n in dsl.window_params(candidate):
                for factor in (0.75, 1.25):
                    n2 = max(dsl.N_MIN, min(dsl.N_MAX, int(n * factor)))
                    if n2 == n:
                        continue
                    node["n"] = n2
                    neighbor_sharpes.append(self._score_on(candidate, closes)[0])
                    node["n"] = n
            asset_sharpes.append(sr)
            asset_robusts.append(min([sr, *neighbor_sharpes]) if neighbor_sharpes else sr)
            per_asset[sym] = s

        train_sharpe = sum(asset_sharpes) / len(asset_sharpes)
        robust = min(asset_robusts)

        # Degenerate filters: must actually trade on every asset.
        min_trades = min(s.get("trades", 0) for s in per_asset.values())
        min_expo = min(s.get("exposure", 0) for s in per_asset.values())
        if len(per_asset) == 1:
            s = next(iter(per_asset.values()))
        else:
            s = {"per_asset": per_asset, "trades": min_trades, "exposure": min_expo}
        if min_trades < 4 or min_expo < 0.02:
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


def finalize_multi(
    closes_map_full: dict[str, list[float]],
    search_len: int,
    conn: sqlite3.Connection,
    top_m: int = 3,
) -> dict:
    """Multi-asset judgement day: finalists judged on the EQUAL-WEIGHT BASKET
    of their per-asset holdout returns, vs the equal-weight B&H basket."""
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

    boundary = search_len
    bench_per_asset = {
        sym: engine.buy_and_hold(closes[boundary - 1 :], FEE_BPS, SLIP_BPS).returns
        for sym, closes in closes_map_full.items()
    }
    n_bars = min(len(r) for r in bench_per_asset.values())
    bench_basket = [
        sum(rets[t] for rets in bench_per_asset.values()) / len(bench_per_asset)
        for t in range(n_bars)
    ]

    results = []
    for h, canon, tr_sr, rob_sr in finalists:
        cand = json.loads(canon)
        strat_per_asset = []
        per_asset_stats = {}
        for sym, closes in closes_map_full.items():
            w = interpret.weights(cand, closes)
            res = engine.run(closes[boundary - 1 :], w[boundary - 1 :], FEE_BPS, SLIP_BPS)
            strat_per_asset.append(res.returns)
            per_asset_stats[sym] = res.stats
        basket = [
            sum(rets[t] for rets in strat_per_asset) / len(strat_per_asset)
            for t in range(n_bars)
        ]
        excess = [a - b for a, b in zip(basket, bench_basket)]
        dsr = stats.deflated_sharpe(basket, n_trials, trial_sharpes)
        pval = stats.stationary_bootstrap_pvalue(excess)
        entry = {
            "hash": h,
            "candidate": cand,
            "train_sharpe": tr_sr,
            "robust_sharpe": rob_sr,
            "holdout_basket": metricsummary(basket),
            "per_asset": per_asset_stats,
            "holdout_vs_bh_pvalue": pval,
            "dsr": dsr,
            "verdict": "PASS" if dsr["dsr"] >= 0.95 and pval <= 0.05 else "FAIL",
        }
        results.append(entry)
        conn.execute(
            "INSERT OR REPLACE INTO lab_finals VALUES (?,?,?)",
            (h, int(time.time() * 1000), json.dumps(entry, default=str)),
        )
    conn.commit()
    return {
        "n_trials": n_trials,
        "holdout_bars": n_bars,
        "benchmark_basket": metricsummary(bench_basket),
        "finalists": results,
    }


def metricsummary(returns: list[float]) -> dict:
    from ..backtest import metrics

    return metrics.summarize(returns)
