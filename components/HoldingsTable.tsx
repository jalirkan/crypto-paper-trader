"use client";

import { coinLabel } from "@/lib/coins";
import { fmtPct, fmtQty, fmtUsd } from "@/lib/format";
import { usePortfolio } from "@/lib/store";
import type { PriceMap } from "@/lib/types";

interface Props {
  prices: PriceMap;
  onTrade: (coinId: string) => void;
}

export default function HoldingsTable({ prices, onTrade }: Props) {
  const { state } = usePortfolio();
  const holdings = Object.values(state.holdings).filter((h) => h.qty > 0);

  if (holdings.length === 0) {
    return <div className="empty">No positions yet — hit Trade on any asset to start.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Asset</th>
            <th className="r">Qty</th>
            <th className="r">Avg Cost</th>
            <th className="r">Value</th>
            <th className="r">Unrealized P&L</th>
            <th className="r"></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const price = prices[h.coinId]?.price;
            const value = price ? h.qty * price : null;
            const pnl = price ? (price - h.avgCost) * h.qty : null;
            const pnlPct = price ? ((price - h.avgCost) / h.avgCost) * 100 : null;
            return (
              <tr key={h.coinId}>
                <td className="coin-name">{coinLabel(h.coinId)}</td>
                <td className="r num">{fmtQty(h.qty)}</td>
                <td className="r num dim">{fmtUsd(h.avgCost)}</td>
                <td className="r num">{value != null ? fmtUsd(value) : "—"}</td>
                <td className={`r num ${(pnl ?? 0) >= 0 ? "up" : "down"}`}>
                  {pnl != null ? `${fmtUsd(pnl)} (${fmtPct(pnlPct!)})` : "—"}
                </td>
                <td className="r">
                  <button className="btn sm" onClick={() => onTrade(h.coinId)}>
                    Trade
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
