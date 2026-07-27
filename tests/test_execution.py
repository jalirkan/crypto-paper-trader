"""OMS chaos tests — every distributed-systems trap we could script."""

import unittest

from execution.mock_exchange import MockExchange
from execution.oms import OrderManager
from execution.reconcile import reconcile
from execution.risk import RiskConfig, RiskGuard
from execution.store import Journal
from execution.target import TargetConfig, compute_intent
from execution.types import OrderIntent


def rig(behaviors=None, duplicate_reports=False, risk_cfg=None):
    j = Journal(":memory:")
    x = MockExchange(behaviors=behaviors, duplicate_reports=duplicate_reports)
    x.set_mark("BTC", 100.0)
    r = RiskGuard(j, risk_cfg or RiskConfig())
    return j, x, r, OrderManager(j, x, r)


def intent(key="k1", side="buy", qty=1.0, px=100.0):
    return OrderIntent(symbol="BTC", side=side, qty=qty, limit_px=px, intent_key=key)


class TestHappyPath(unittest.TestCase):
    def test_place_fill_position(self):
        j, x, r, oms = rig()
        o = oms.place(intent())
        self.assertEqual(o.state, "OPEN")
        x.fill(o.client_id, 1.0, 99.5)
        self.assertEqual(oms.poll_fills(), 1)
        o2 = j.get_order(o.client_id)
        self.assertEqual(o2.state, "FILLED")
        self.assertAlmostEqual(o2.avg_px, 99.5)
        self.assertAlmostEqual(j.position("BTC"), 1.0)

    def test_partial_fills_accumulate(self):
        j, x, r, oms = rig()
        o = oms.place(intent(qty=2.0))
        x.fill(o.client_id, 0.7, 100.0)
        oms.poll_fills()
        self.assertEqual(j.get_order(o.client_id).state, "PARTIALLY_FILLED")
        x.fill(o.client_id, 1.3, 101.0)
        oms.poll_fills()
        o2 = j.get_order(o.client_id)
        self.assertEqual(o2.state, "FILLED")
        self.assertAlmostEqual(o2.filled_qty, 2.0)
        self.assertAlmostEqual(o2.avg_px, (0.7 * 100 + 1.3 * 101) / 2.0)

    def test_place_is_idempotent_on_intent(self):
        j, x, r, oms = rig()
        o1 = oms.place(intent("same-key"))
        o2 = oms.place(intent("same-key"))
        self.assertEqual(o1.client_id, o2.client_id)
        self.assertEqual(len(x.orders), 1)  # exchange saw exactly one order


class TestLostAck(unittest.TestCase):
    def test_drop_ack_goes_unknown_then_reconcile_adopts_no_duplicate(self):
        j, x, r, oms = rig(behaviors=["drop_ack"])
        o = oms.place(intent("lost-1"))
        self.assertEqual(o.state, "UNKNOWN")  # never assume failure

        # The order actually lives on the exchange; it even fills while we're blind.
        x.fill(o.client_id, 1.0, 100.0)

        rep = reconcile(j, x, oms, r, ["BTC"])
        self.assertEqual(rep["resolved"], 1)
        o2 = j.get_order(o.client_id)
        self.assertEqual(o2.state, "FILLED")
        self.assertAlmostEqual(j.position("BTC"), 1.0)
        self.assertFalse(rep["drift_frozen"])  # journal and exchange agree

        # Retry of the same intent after adoption must NOT double-place.
        oms.place(intent("lost-1"))
        self.assertEqual(len(x.orders), 1)

    def test_truly_never_seen_becomes_rejected(self):
        j, x, r, oms = rig(behaviors=["reject"])
        o = oms.place(intent("nope"))
        self.assertEqual(o.state, "REJECTED")
        # And a manufactured UNKNOWN with no exchange record resolves to REJECTED.
        from execution.types import Order

        ghost = Order(client_id="cpt-ghost", symbol="BTC", side="buy", qty=1, limit_px=100)
        ghost.state = "UNKNOWN"
        j.write_order(ghost)
        reconcile(j, x, oms, r, ["BTC"])
        self.assertEqual(j.get_order("cpt-ghost").state, "REJECTED")


class TestDuplicatesAndCrash(unittest.TestCase):
    def test_duplicate_trade_reports_apply_once(self):
        j, x, r, oms = rig(duplicate_reports=True)
        o = oms.place(intent())
        x.fill(o.client_id, 1.0, 100.0)
        self.assertEqual(oms.poll_fills(), 1)  # two reports, one application
        self.assertAlmostEqual(j.position("BTC"), 1.0)
        self.assertEqual(oms.poll_fills(), 0)  # re-poll: nothing new

    def test_crash_recovery_new_oms_same_journal(self):
        j = Journal(":memory:")
        x = MockExchange(behaviors=["ack", "drop_ack"])
        x.set_mark("BTC", 100.0)
        r = RiskGuard(j)
        oms1 = OrderManager(j, x, r)
        a = oms1.place(intent("a", qty=1.0))
        b = oms1.place(intent("b", qty=0.5))  # ack lost → UNKNOWN
        x.fill(a.client_id, 1.0, 100.0)
        x.fill(b.client_id, 0.5, 100.0)
        # 💥 process dies before polling. New OMS instance, same journal+exchange:
        oms2 = OrderManager(j, x, RiskGuard(j))
        rep = reconcile(j, x, oms2, RiskGuard(j), ["BTC"])
        self.assertGreaterEqual(rep["resolved"], 1)
        self.assertAlmostEqual(j.position("BTC"), 1.5)
        self.assertFalse(rep["drift_frozen"])

    def test_position_drift_freezes_never_trades(self):
        j, x, r, oms = rig()
        o = oms.place(intent())
        x.fill(o.client_id, 1.0, 100.0)
        oms.poll_fills()
        # Corrupt the journal to simulate drift (e.g. manual trade on exchange).
        j.conn.execute("DELETE FROM fills")
        j.conn.commit()
        rep = reconcile(j, x, oms, r, ["BTC"])
        self.assertTrue(rep["drift_frozen"])
        self.assertIn("position drift", r.killed())
        # Frozen means frozen: new risk-increasing orders are refused.
        o2 = oms.place(intent("post-freeze"))
        self.assertEqual(o2.state, "REJECTED")
        self.assertIn("kill switch", o2.reason)


class TestRisk(unittest.TestCase):
    def test_oversized_order_never_reaches_exchange(self):
        j, x, r, oms = rig(risk_cfg=RiskConfig(max_order_notional=50))
        o = oms.place(intent(qty=1.0, px=100.0))  # notional 100 > 50
        self.assertEqual(o.state, "REJECTED")
        self.assertEqual(len(x.orders), 0)

    def test_price_band(self):
        j, x, r, oms = rig()
        o = oms.place(intent(px=150.0))  # mark 100, band ±5%
        self.assertEqual(o.state, "REJECTED")
        self.assertIn("outside", o.reason)

    def test_daily_loss_kill_and_reduce_only(self):
        j, x, r, oms = rig()
        buy = oms.place(intent("pre", qty=0.5))
        x.fill(buy.client_id, 0.5, 100.0)
        oms.poll_fills()
        r.check_daily_loss(1000.0)  # baseline
        r.check_daily_loss(1000.0 * 0.85)  # −15% > 10% limit → kill
        self.assertIsNotNone(r.killed())
        blocked = oms.place(intent("more", side="buy", qty=0.1))
        self.assertEqual(blocked.state, "REJECTED")
        flatten = oms.place(intent("flatten", side="sell", qty=0.5))
        self.assertEqual(flatten.state, "OPEN")  # reducing risk is allowed


class TestTargeter(unittest.TestCase):
    def test_full_cycle_in_and_out(self):
        j, x, r, oms = rig()
        it = compute_intent(j, "BTC", 1.0, equity=200.0, mark=100.0, intent_key="t1")
        self.assertEqual(it.side, "buy")
        self.assertAlmostEqual(it.qty, 2.0, places=5)
        o = oms.place(it)
        x.fill(o.client_id, it.qty, 100.0)
        oms.poll_fills()
        # At target → no order.
        self.assertIsNone(compute_intent(j, "BTC", 1.0, 200.0, 100.0, "t2"))
        out = compute_intent(j, "BTC", 0.0, 200.0, 100.0, "t3")
        self.assertEqual(out.side, "sell")
        self.assertAlmostEqual(out.qty, 2.0, places=5)

    def test_working_orders_prevent_stacking(self):
        j, x, r, oms = rig()
        it = compute_intent(j, "BTC", 1.0, 200.0, 100.0, "w1")
        oms.place(it)  # OPEN, unfilled
        # Same cycle logic re-runs before the fill arrives → nothing new.
        self.assertIsNone(compute_intent(j, "BTC", 1.0, 200.0, 100.0, "w2"))

    def test_dust_and_short_guard(self):
        j, x, r, oms = rig()
        # Tiny drift below tolerance → no order.
        self.assertIsNone(
            compute_intent(j, "BTC", 0.001, 200.0, 100.0, "d1",
                           cfg=TargetConfig(min_notional=5.0))
        )
        # Sell with no position → never short.
        self.assertIsNone(compute_intent(j, "BTC", 0.0, 200.0, 100.0, "d2"))

    def test_stale_orders_get_canceled(self):
        j, x, r, oms = rig()
        o = oms.place(intent())
        n = oms.cancel_stale(ttl_ms=1000, now=o.created_ts + 5000)
        self.assertEqual(n, 1)
        self.assertEqual(j.get_order(o.client_id).state, "CANCELED")


if __name__ == "__main__":
    unittest.main()
