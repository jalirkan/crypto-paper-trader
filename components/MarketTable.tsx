"use client";

import { COINS } from "@/lib/coins";
import { fmtPct, fmtUsd } from "@/lib/format";
import type { PriceMap } from "@/lib/types";

interface Props {
  prices: PriceMap;
  onTrade: (coinId: string) => void;
}

export default function MarketTable({ prices, onTrade }: Props) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Asset</th>
            <th className="r">Price</th>
            <th className="r">24h</th>
            <th className="r">Market Cap</th>
            <th className="r">Volume 24h</th>
            <th className="r"></th>
          </tr>
        </thead>
        <tbody>
          {COINS.map((coin) => {
            const p = prices[coin.id];
            const change = p?.change24h ?? 0;
            return (
              <tr key={coin.id}>
                <td>
                  <div className="coin-cell">
                    <div
                      className="coin-icon"
                      style={{ background: `${coin.color}22`, color: coin.color }}
                    >
                      {coin.symbol.slice(0, 4)}
                    </div>
                    <div>
                      <div className="coin-name">{coin.name}</div>
                      <div className="coin-sym">{coin.symbol}</div>
                    </div>
                  </div>
                </td>
                <td className="r num">{p ? fmtUsd(p.price) : "—"}</td>
                <td className={`r num ${change >= 0 ? "up" : "down"}`}>
                  {p ? fmtPct(change) : "—"}
                </td>
                <td className="r num dim">{p ? fmtUsd(p.marketCap, true) : "—"}</td>
                <td className="r num dim">{p ? fmtUsd(p.volume24h, true) : "—"}</td>
                <td className="r">
                  <button
                    className="btn sm primary"
                    onClick={() => onTrade(coin.id)}
                    disabled={!p}
                  >
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
