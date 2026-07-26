"use client";

import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import { uid } from "./format";
import type {
  BotConfig,
  PortfolioState,
  PriceMap,
  Signal,
  Trade,
  TradeSide,
  TradeSource,
} from "./types";

const STORAGE_KEY = "cpt-portfolio-v1";
const STARTING_CASH = 100_000;
const EPSILON = 1e-9;
const MAX_EQUITY_POINTS = 1000;
const MAX_TRADES = 500;

export const initialState: PortfolioState = {
  startingCash: STARTING_CASH,
  cash: STARTING_CASH,
  holdings: {},
  trades: [],
  bots: [],
  equityHistory: [],
};

export type Action =
  | { type: "HYDRATE"; state: PortfolioState }
  | {
      type: "TRADE";
      coinId: string;
      side: TradeSide;
      qty: number;
      price: number;
      source: TradeSource;
      note?: string;
      botId?: string;
    }
  | { type: "ADD_BOT"; bot: BotConfig }
  | { type: "UPDATE_BOT"; id: string; patch: Partial<BotConfig> }
  | { type: "REMOVE_BOT"; id: string }
  | { type: "BOT_RESULT"; id: string; signal: Signal; ts: number }
  | { type: "SNAPSHOT"; t: number; value: number }
  | { type: "RESET" };

export function reducer(state: PortfolioState, action: Action): PortfolioState {
  switch (action.type) {
    case "HYDRATE":
      return action.state;

    case "TRADE": {
      const { coinId, side, price, source, note, botId } = action;
      let qty = action.qty;
      if (!(qty > 0) || !(price > 0)) return state;

      const holding = state.holdings[coinId];

      if (side === "buy") {
        const cost = qty * price;
        if (cost > state.cash + EPSILON) return state; // insufficient cash

        const prevQty = holding?.qty ?? 0;
        const prevAvg = holding?.avgCost ?? 0;
        const newQty = prevQty + qty;
        const avgCost = (prevQty * prevAvg + qty * price) / newQty;

        const trade: Trade = {
          id: uid(),
          ts: Date.now(),
          coinId,
          side,
          qty,
          price,
          value: cost,
          source,
          note,
        };

        return {
          ...state,
          cash: state.cash - cost,
          holdings: {
            ...state.holdings,
            [coinId]: { coinId, qty: newQty, avgCost },
          },
          trades: [...state.trades, trade].slice(-MAX_TRADES),
          bots: botId
            ? state.bots.map((b) =>
                b.id === botId ? { ...b, positionQty: b.positionQty + qty } : b
              )
            : state.bots,
        };
      }

      // sell
      if (!holding || holding.qty <= EPSILON) return state;
      qty = Math.min(qty, holding.qty);
      const proceeds = qty * price;
      const realizedPnl = (price - holding.avgCost) * qty;
      const remaining = holding.qty - qty;

      const trade: Trade = {
        id: uid(),
        ts: Date.now(),
        coinId,
        side,
        qty,
        price,
        value: proceeds,
        source,
        note,
        realizedPnl,
      };

      const holdings = { ...state.holdings };
      if (remaining <= EPSILON) delete holdings[coinId];
      else holdings[coinId] = { ...holding, qty: remaining };

      return {
        ...state,
        cash: state.cash + proceeds,
        holdings,
        trades: [...state.trades, trade].slice(-MAX_TRADES),
        bots: botId
          ? state.bots.map((b) =>
              b.id === botId
                ? { ...b, positionQty: Math.max(0, b.positionQty - qty) }
                : b
            )
          : state.bots,
      };
    }

    case "ADD_BOT":
      return { ...state, bots: [...state.bots, action.bot] };

    case "UPDATE_BOT":
      return {
        ...state,
        bots: state.bots.map((b) =>
          b.id === action.id ? { ...b, ...action.patch } : b
        ),
      };

    case "REMOVE_BOT":
      return { ...state, bots: state.bots.filter((b) => b.id !== action.id) };

    case "BOT_RESULT":
      return {
        ...state,
        bots: state.bots.map((b) =>
          b.id === action.id
            ? { ...b, lastSignal: action.signal, lastRunTs: action.ts }
            : b
        ),
      };

    case "SNAPSHOT": {
      const lastPoint = state.equityHistory[state.equityHistory.length - 1];
      // Keep at most one point per 60s.
      if (lastPoint && action.t - lastPoint.t < 60_000) return state;
      return {
        ...state,
        equityHistory: [
          ...state.equityHistory,
          { t: action.t, value: action.value },
        ].slice(-MAX_EQUITY_POINTS),
      };
    }

    case "RESET":
      return { ...initialState };

    default:
      return state;
  }
}

/** Total account value: cash + market value of holdings. */
export function computeEquity(state: PortfolioState, prices: PriceMap): number {
  let equity = state.cash;
  for (const h of Object.values(state.holdings)) {
    const p = prices[h.coinId]?.price;
    if (p) equity += h.qty * p;
  }
  return equity;
}

interface StoreValue {
  state: PortfolioState;
  dispatch: Dispatch<Action>;
}

const StoreContext = createContext<StoreValue | null>(null);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // Hydrate from localStorage once on mount.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as PortfolioState;
        if (typeof saved.cash === "number" && saved.holdings) {
          dispatch({ type: "HYDRATE", state: { ...initialState, ...saved } });
        }
      }
    } catch {
      // Corrupt state — start fresh.
    }
  }, []);

  // Persist on every change.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Storage full or unavailable — non-fatal.
    }
  }, [state]);

  return (
    <StoreContext.Provider value={{ state, dispatch }}>
      {children}
    </StoreContext.Provider>
  );
}

export function usePortfolio(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("usePortfolio must be used within PortfolioProvider");
  return ctx;
}
