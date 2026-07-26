"use client";

import { useEffect, useState } from "react";
import AdvisorPanel from "./AdvisorPanel";
import BotsPanel from "./BotsPanel";
import EquityChart from "./EquityChart";
import HoldingsTable from "./HoldingsTable";
import MarketTable from "./MarketTable";
import PortfolioSummary from "./PortfolioSummary";
import TradeLog from "./TradeLog";
import TradeModal from "./TradeModal";
import { useBotRunner, usePrices } from "@/lib/hooks";
import { computeEquity, PortfolioProvider, usePortfolio } from "@/lib/store";

export default function Dashboard() {
  return (
    <PortfolioProvider>
      <DashboardInner />
    </PortfolioProvider>
  );
}

function DashboardInner() {
  const { state, dispatch } = usePortfolio();
  const { prices, error, lastUpdated } = usePrices();
  const [tradeCoin, setTradeCoin] = useState<string | null>(null);

  useBotRunner(prices);

  // Record an equity snapshot whenever fresh prices arrive (throttled in reducer).
  useEffect(() => {
    if (Object.keys(prices).length === 0) return;
    dispatch({ type: "SNAPSHOT", t: Date.now(), value: computeEquity(state, prices) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prices, dispatch]);

  return (
    <div className="container">
      <header className="app-header">
        <div className="app-title">
          <div className="logo">📈</div>
          Crypto Paper Trader
          <span className="tag">Simulated</span>
        </div>
        <div className="header-meta">
          {error ? (
            <span className="error-text">{error}</span>
          ) : (
            <span>
              <span className="pulse" />
              {lastUpdated
                ? `Live · updated ${new Date(lastUpdated).toLocaleTimeString()}`
                : "Connecting…"}
            </span>
          )}
          <button
            className="btn sm ghost"
            title="Reset portfolio to $100,000"
            onClick={() => {
              if (window.confirm("Reset portfolio, trades and bots?")) {
                dispatch({ type: "RESET" });
              }
            }}
          >
            Reset
          </button>
        </div>
      </header>

      <div style={{ marginBottom: 20 }}>
        <PortfolioSummary prices={prices} />
      </div>

      <div className="grid">
        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>Portfolio</h2>
            </div>
            <div className="panel-body">
              <EquityChart
                points={state.equityHistory}
                baseline={state.startingCash}
              />
            </div>
            <HoldingsTable prices={prices} onTrade={setTradeCoin} />
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Market</h2>
            </div>
            <div className="panel-body flush">
              <MarketTable prices={prices} onTrade={setTradeCoin} />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Activity</h2>
            </div>
            <div className="panel-body flush">
              <TradeLog />
            </div>
          </section>
        </div>

        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>Strategy Bots</h2>
            </div>
            <div className="panel-body">
              <BotsPanel prices={prices} />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>AI Advisor</h2>
            </div>
            <div className="panel-body">
              <AdvisorPanel prices={prices} />
            </div>
          </section>
        </div>
      </div>

      {tradeCoin && (
        <TradeModal
          coinId={tradeCoin}
          prices={prices}
          onClose={() => setTradeCoin(null)}
        />
      )}
    </div>
  );
}
