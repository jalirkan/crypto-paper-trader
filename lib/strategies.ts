import { macd, rsi, sma } from "./indicators";
import type { Signal } from "./types";

export interface ParamDef {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  params: ParamDef[];
  defaults: Record<string, number>;
  /** Evaluate the latest signal from a series of closing prices (oldest → newest). */
  evaluate(prices: number[], params: Record<string, number>): Signal;
}

const fmt = (n: number) =>
  n >= 1000
    ? n.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : n.toLocaleString("en-US", { maximumFractionDigits: 4 });

/** Values at the last two closed points of a series (ignoring NaN warm-up). */
function lastTwo(series: number[]): [number, number] | null {
  const idx: number[] = [];
  for (let i = series.length - 1; i >= 0 && idx.length < 2; i--) {
    if (!Number.isNaN(series[i])) idx.unshift(i);
  }
  if (idx.length < 2) return null;
  return [series[idx[0]], series[idx[1]]];
}

const smaCross: Strategy = {
  id: "sma-cross",
  name: "SMA Crossover",
  description:
    "Buys when the fast moving average crosses above the slow one (golden cross), sells on the opposite cross.",
  params: [
    { key: "fast", label: "Fast period", min: 3, max: 50, step: 1 },
    { key: "slow", label: "Slow period", min: 10, max: 200, step: 1 },
  ],
  defaults: { fast: 10, slow: 30 },
  evaluate(prices, params) {
    const fast = sma(prices, params.fast);
    const slow = sma(prices, params.slow);
    const f = lastTwo(fast);
    const s = lastTwo(slow);
    if (!f || !s) return { action: "hold", reason: "Not enough data yet." };

    const [fPrev, fNow] = f;
    const [sPrev, sNow] = s;
    if (fPrev <= sPrev && fNow > sNow) {
      return {
        action: "buy",
        reason: `SMA${params.fast} (${fmt(fNow)}) crossed above SMA${params.slow} (${fmt(sNow)}) — bullish crossover.`,
      };
    }
    if (fPrev >= sPrev && fNow < sNow) {
      return {
        action: "sell",
        reason: `SMA${params.fast} (${fmt(fNow)}) crossed below SMA${params.slow} (${fmt(sNow)}) — bearish crossover.`,
      };
    }
    return {
      action: "hold",
      reason: `SMA${params.fast} ${fNow > sNow ? "above" : "below"} SMA${params.slow} (${fmt(fNow)} vs ${fmt(sNow)}), no fresh cross.`,
    };
  },
};

const rsiReversion: Strategy = {
  id: "rsi-reversion",
  name: "RSI Mean Reversion",
  description:
    "Buys when RSI drops below the oversold threshold, sells when it rises above the overbought threshold.",
  params: [
    { key: "period", label: "RSI period", min: 5, max: 30, step: 1 },
    { key: "oversold", label: "Oversold", min: 10, max: 45, step: 1 },
    { key: "overbought", label: "Overbought", min: 55, max: 90, step: 1 },
  ],
  defaults: { period: 14, oversold: 30, overbought: 70 },
  evaluate(prices, params) {
    const series = rsi(prices, params.period);
    const pair = lastTwo(series);
    if (!pair) return { action: "hold", reason: "Not enough data yet." };
    const [, now] = pair;
    const val = now.toFixed(1);
    if (now <= params.oversold) {
      return {
        action: "buy",
        reason: `RSI(${params.period}) at ${val} — below oversold threshold ${params.oversold}.`,
      };
    }
    if (now >= params.overbought) {
      return {
        action: "sell",
        reason: `RSI(${params.period}) at ${val} — above overbought threshold ${params.overbought}.`,
      };
    }
    return {
      action: "hold",
      reason: `RSI(${params.period}) at ${val}, inside the ${params.oversold}–${params.overbought} neutral band.`,
    };
  },
};

const macdMomentum: Strategy = {
  id: "macd-momentum",
  name: "MACD Momentum",
  description:
    "Buys when the MACD histogram flips positive (momentum turning up), sells when it flips negative.",
  params: [
    { key: "fast", label: "Fast EMA", min: 5, max: 20, step: 1 },
    { key: "slow", label: "Slow EMA", min: 15, max: 50, step: 1 },
    { key: "signal", label: "Signal", min: 3, max: 20, step: 1 },
  ],
  defaults: { fast: 12, slow: 26, signal: 9 },
  evaluate(prices, params) {
    const { histogram } = macd(prices, params.fast, params.slow, params.signal);
    const pair = lastTwo(histogram);
    if (!pair) return { action: "hold", reason: "Not enough data yet." };
    const [prev, now] = pair;
    if (prev <= 0 && now > 0) {
      return {
        action: "buy",
        reason: `MACD histogram flipped positive (${now.toFixed(3)}) — upward momentum shift.`,
      };
    }
    if (prev >= 0 && now < 0) {
      return {
        action: "sell",
        reason: `MACD histogram flipped negative (${now.toFixed(3)}) — downward momentum shift.`,
      };
    }
    return {
      action: "hold",
      reason: `MACD histogram ${now >= 0 ? "positive" : "negative"} (${now.toFixed(3)}), no fresh flip.`,
    };
  },
};

export const STRATEGIES: Strategy[] = [smaCross, rsiReversion, macdMomentum];

export const STRATEGY_MAP: Record<string, Strategy> = Object.fromEntries(
  STRATEGIES.map((s) => [s.id, s])
);
