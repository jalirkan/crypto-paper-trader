import type { Coin } from "./types";

/** Tracked universe. Ids are CoinGecko ids. */
export const COINS: Coin[] = [
  { id: "bitcoin", symbol: "BTC", name: "Bitcoin", color: "#f7931a" },
  { id: "ethereum", symbol: "ETH", name: "Ethereum", color: "#627eea" },
  { id: "solana", symbol: "SOL", name: "Solana", color: "#9945ff" },
  { id: "binancecoin", symbol: "BNB", name: "BNB", color: "#f0b90b" },
  { id: "ripple", symbol: "XRP", name: "XRP", color: "#00a5df" },
  { id: "cardano", symbol: "ADA", name: "Cardano", color: "#0033ad" },
  { id: "dogecoin", symbol: "DOGE", name: "Dogecoin", color: "#c2a633" },
  { id: "avalanche-2", symbol: "AVAX", name: "Avalanche", color: "#e84142" },
  { id: "chainlink", symbol: "LINK", name: "Chainlink", color: "#2a5ada" },
  { id: "litecoin", symbol: "LTC", name: "Litecoin", color: "#8a92b2" },
];

export const COIN_MAP: Record<string, Coin> = Object.fromEntries(
  COINS.map((c) => [c.id, c])
);

export function coinLabel(coinId: string): string {
  const c = COIN_MAP[coinId];
  return c ? c.symbol : coinId.toUpperCase();
}
