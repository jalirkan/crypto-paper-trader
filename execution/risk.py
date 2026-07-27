"""Pre-trade risk guards and the kill switch.

Every order passes through `check()` — a single choke point. The kill switch
persists in the journal, so a restart cannot forget that trading was halted.
Once killed, only explicit human action (`clear_kill`) re-arms the system;
the OMS itself may only reduce risk (flatten) while killed.
"""

from __future__ import annotations

from .store import Journal
from .types import OrderIntent


class RiskConfig:
    def __init__(
        self,
        max_order_notional: float = 250.0,
        max_position_notional: float = 500.0,
        price_band_pct: float = 0.05,
        daily_loss_limit_pct: float = 0.10,
    ):
        self.max_order_notional = max_order_notional
        self.max_position_notional = max_position_notional
        self.price_band_pct = price_band_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct


class RiskGuard:
    def __init__(self, journal: Journal, cfg: RiskConfig | None = None):
        self.j = journal
        self.cfg = cfg or RiskConfig()

    # ---- kill switch ----

    def killed(self) -> str | None:
        return self.j.get_meta("kill_switch")

    def kill(self, reason: str) -> None:
        self.j.set_meta("kill_switch", reason)
        self.j.event("KILL", reason)

    def clear_kill(self) -> None:
        """Explicit human action only — never called by the OMS itself."""
        self.j.set_meta("kill_switch", "")
        self.j.event("KILL_CLEARED", "manual")

    # ---- equity-based daily stop ----

    def check_daily_loss(self, equity: float) -> None:
        """Call each cycle with current equity; arms/uses a daily baseline."""
        import time

        today = time.strftime("%Y-%m-%d")
        baseline_day = self.j.get_meta("equity_day")
        if baseline_day != today:
            self.j.set_meta("equity_day", today)
            self.j.set_meta("equity_baseline", str(equity))
            return
        baseline = float(self.j.get_meta("equity_baseline", str(equity)) or equity)
        if baseline > 0 and (equity / baseline - 1) < -self.cfg.daily_loss_limit_pct:
            self.kill(
                f"daily loss limit: equity {equity:.2f} vs baseline {baseline:.2f}"
            )

    # ---- pre-trade ----

    def check(
        self,
        intent: OrderIntent,
        mark: float,
        position_qty: float,
        reduce_only_ok: bool = True,
    ) -> str | None:
        """Returns a rejection reason, or None if the order may proceed."""
        killed = self.killed()
        is_reducing = (intent.side == "sell" and position_qty > 0) or (
            intent.side == "buy" and position_qty < 0
        )
        if killed:
            if not (reduce_only_ok and is_reducing):
                return f"kill switch active: {killed}"

        if intent.qty <= 0:
            return "non-positive quantity"
        if intent.notional > self.cfg.max_order_notional:
            return (
                f"order notional {intent.notional:.2f} > cap {self.cfg.max_order_notional:.2f}"
            )

        band = self.cfg.price_band_pct
        if mark > 0 and not (mark * (1 - band) <= intent.limit_px <= mark * (1 + band)):
            return f"limit {intent.limit_px:.2f} outside ±{band:.0%} of mark {mark:.2f}"

        signed = intent.qty if intent.side == "buy" else -intent.qty
        post = abs((position_qty + signed) * mark)
        if not is_reducing and post > self.cfg.max_position_notional:
            return (
                f"post-trade position {post:.2f} > cap {self.cfg.max_position_notional:.2f}"
            )
        return None
