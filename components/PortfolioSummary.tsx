"use client";

import { fmtPct, fmtUsd } from "@/lib/format";
import { computeEquity, usePortfolio } from "@/lib/store";
import type { PriceMap } from "@/lib/types";

export default function PortfolioSummary({ prices }: { prices: PriceMap }) {
  const { state } = usePortfolio();

  const equity = computeEquity(state, prices);
  const totalPnl = equity - state.startingCash;
  const totalPnlPct = (totalPnl / state.startingCash) * 100;

  let unrealized = 0;
  let invested = 0;
  for (const h of Object.values(state.holdings)) {
    const p = prices[h.coinId]?.price;
    if (p) {
      unrealized += (p - h.avgCost) * h.qty;
      invested += h.qty * p;
    }
  }

  const realized = state.trades.reduce((sum, t) => sum + (t.realizedPnl ?? 0), 0);

  return (
    <div className="stats-row">
      <div className="stat">
        <div className="label">Total Equity</div>
        <div className="value num">{fmtUsd(equity)}</div>
        <div className={`sub num ${totalPnl >= 0 ? "up" : "down"}`}>
          {fmtUsd(totalPnl)} ({fmtPct(totalPnlPct)}) all-time
        </div>
      </div>
      <div className="stat">
        <div className="label">Cash</div>
        <div className="value num">{fmtUsd(state.cash)}</div>
        <div className="sub">available to trade</div>
      </div>
      <div className="stat">
        <div className="label">Invested</div>
        <div className="value num">{fmtUsd(invested)}</div>
        <div className={`sub num ${unrealized >= 0 ? "up" : "down"}`}>
          {fmtUsd(unrealized)} unrealized
        </div>
      </div>
      <div className="stat">
        <div className="label">Realized P&L</div>
        <div className={`value num ${realized >= 0 ? "up" : "down"}`}>
          {fmtUsd(realized)}
        </div>
        <div className="sub">{state.trades.length} trades</div>
      </div>
    </div>
  );
}
