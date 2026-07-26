"use client";

import { coinLabel } from "@/lib/coins";
import { fmtQty, fmtTime, fmtUsd } from "@/lib/format";
import { usePortfolio } from "@/lib/store";

export default function TradeLog() {
  const { state } = usePortfolio();
  const trades = [...state.trades].reverse();

  if (trades.length === 0) {
    return <div className="empty">Trades will show up here — manual, bot and AI alike.</div>;
  }

  return (
    <div style={{ overflowX: "auto", maxHeight: 360, overflowY: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Source</th>
            <th>Side</th>
            <th>Asset</th>
            <th className="r">Qty</th>
            <th className="r">Price</th>
            <th className="r">Value</th>
            <th className="r">Realized</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} title={t.note ?? ""}>
              <td className="dim num">{fmtTime(t.ts)}</td>
              <td>
                <span className={`badge ${t.source}`}>{t.source}</span>
              </td>
              <td>
                <span className={`badge ${t.side}`}>{t.side}</span>
              </td>
              <td className="coin-name">{coinLabel(t.coinId)}</td>
              <td className="r num">{fmtQty(t.qty)}</td>
              <td className="r num dim">{fmtUsd(t.price)}</td>
              <td className="r num">{fmtUsd(t.value)}</td>
              <td
                className={`r num ${
                  t.realizedPnl == null ? "faint" : t.realizedPnl >= 0 ? "up" : "down"
                }`}
              >
                {t.realizedPnl != null ? fmtUsd(t.realizedPnl) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
