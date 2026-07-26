"use client";

import { useState } from "react";
import PriceChart from "./PriceChart";
import { COIN_MAP } from "@/lib/coins";
import { fmtPct, fmtQty, fmtUsd } from "@/lib/format";
import { usePortfolio } from "@/lib/store";
import type { PriceMap } from "@/lib/types";

interface Props {
  coinId: string;
  prices: PriceMap;
  onClose: () => void;
}

export default function TradeModal({ coinId, prices, onClose }: Props) {
  const { state, dispatch } = usePortfolio();
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [usdInput, setUsdInput] = useState("1000");
  const [qtyInput, setQtyInput] = useState("");

  const coin = COIN_MAP[coinId];
  const info = prices[coinId];
  const holding = state.holdings[coinId];

  if (!coin || !info) return null;

  const price = info.price;
  const usd = parseFloat(usdInput) || 0;
  const qty = parseFloat(qtyInput) || 0;

  const buyQty = usd / price;
  const sellValue = qty * price;

  const canBuy = usd >= 1 && usd <= state.cash;
  const canSell = holding != null && qty > 0 && qty <= holding.qty + 1e-12;

  function execute() {
    if (side === "buy" && canBuy) {
      dispatch({
        type: "TRADE",
        coinId,
        side: "buy",
        qty: buyQty,
        price,
        source: "manual",
      });
      onClose();
    } else if (side === "sell" && canSell) {
      dispatch({
        type: "TRADE",
        coinId,
        side: "sell",
        qty,
        price,
        source: "manual",
      });
      onClose();
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <div className="coin-cell">
            <div
              className="coin-icon"
              style={{ background: `${coin.color}22`, color: coin.color }}
            >
              {coin.symbol.slice(0, 4)}
            </div>
            <div>
              <div className="coin-name">{coin.name}</div>
              <div className="coin-sym num">
                {fmtUsd(price)}{" "}
                <span className={info.change24h >= 0 ? "up" : "down"}>
                  {fmtPct(info.change24h)}
                </span>
              </div>
            </div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <PriceChart coinId={coinId} days={7} height={110} />

          <div className="tabs">
            <button
              className={side === "buy" ? "active" : ""}
              onClick={() => setSide("buy")}
            >
              Buy
            </button>
            <button
              className={side === "sell" ? "active" : ""}
              onClick={() => setSide("sell")}
            >
              Sell
            </button>
          </div>

          {side === "buy" ? (
            <>
              <div className="field">
                <label>Amount (USD) — cash: {fmtUsd(state.cash)}</label>
                <input
                  type="number"
                  min="1"
                  step="any"
                  value={usdInput}
                  onChange={(e) => setUsdInput(e.target.value)}
                />
              </div>
              <div className="form-row">
                {[10, 25, 50, 100].map((pct) => (
                  <button
                    key={pct}
                    className="btn sm"
                    style={{ flex: 1 }}
                    onClick={() =>
                      setUsdInput(((state.cash * pct) / 100).toFixed(2))
                    }
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <div className="notice num">
                ≈ {fmtQty(buyQty)} {coin.symbol} at {fmtUsd(price)}
              </div>
              <button className="btn buy" disabled={!canBuy} onClick={execute}>
                Buy {coin.symbol}
              </button>
            </>
          ) : (
            <>
              <div className="field">
                <label>
                  Quantity — held: {holding ? fmtQty(holding.qty) : 0} {coin.symbol}
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={qtyInput}
                  onChange={(e) => setQtyInput(e.target.value)}
                />
              </div>
              <div className="form-row">
                {[25, 50, 75, 100].map((pct) => (
                  <button
                    key={pct}
                    className="btn sm"
                    style={{ flex: 1 }}
                    disabled={!holding}
                    onClick={() =>
                      holding && setQtyInput(((holding.qty * pct) / 100).toString())
                    }
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <div className="notice num">
                ≈ {fmtUsd(sellValue)}
                {holding && qty > 0 && (
                  <>
                    {" "}
                    · P&L: {fmtUsd((price - holding.avgCost) * Math.min(qty, holding.qty))}
                  </>
                )}
              </div>
              <button className="btn sell" disabled={!canSell} onClick={execute}>
                Sell {coin.symbol}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
