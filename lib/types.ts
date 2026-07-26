export interface Coin {
  id: string; // CoinGecko id
  symbol: string;
  name: string;
  color: string; // accent color for the UI
}

export interface PriceInfo {
  price: number;
  change24h: number; // percent
  marketCap: number;
  volume24h: number;
  updatedAt: number; // epoch ms
}

export type PriceMap = Record<string, PriceInfo>;

export type TradeSide = "buy" | "sell";
export type TradeSource = "manual" | "bot" | "ai";

export interface Trade {
  id: string;
  ts: number;
  coinId: string;
  side: TradeSide;
  qty: number;
  price: number;
  value: number; // qty * price in USD
  source: TradeSource;
  note?: string;
  realizedPnl?: number; // set on sells
}

export interface Holding {
  coinId: string;
  qty: number;
  avgCost: number; // average cost basis per unit
}

export type SignalAction = "buy" | "sell" | "hold";

export interface Signal {
  action: SignalAction;
  reason: string;
}

export interface BotConfig {
  id: string;
  coinId: string;
  strategyId: string;
  params: Record<string, number>;
  budgetUsd: number; // max position size the bot manages
  active: boolean;
  positionQty: number; // qty this bot currently holds
  lastSignal?: Signal;
  lastRunTs?: number;
}

export interface EquityPoint {
  t: number;
  value: number;
}

export interface PortfolioState {
  startingCash: number;
  cash: number;
  holdings: Record<string, Holding>;
  trades: Trade[];
  bots: BotConfig[];
  equityHistory: EquityPoint[];
}

export interface AdvisorSuggestion {
  coinId: string;
  action: SignalAction;
  sizeUsd?: number;
  confidence: "low" | "medium" | "high";
  rationale: string;
}

export interface AdvisorTuning {
  botLabel: string;
  suggestion: string;
}

export interface AdvisorResponse {
  assessment: string;
  suggestions: AdvisorSuggestion[];
  tuning: AdvisorTuning[];
  riskNotes: string;
}
