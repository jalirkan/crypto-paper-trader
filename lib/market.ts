import type { PriceMap } from "./types";

/** Client-side fetchers for the app's own API routes. */

export async function fetchPrices(): Promise<PriceMap> {
  const res = await fetch("/api/prices");
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error ?? `Price fetch failed (${res.status})`);
  }
  const data = (await res.json()) as { prices: PriceMap };
  return data.prices;
}

export async function fetchHistory(
  coinId: string,
  days: 1 | 7 | 30 | 90
): Promise<number[][]> {
  const res = await fetch(`/api/history?coin=${coinId}&days=${days}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error ?? `History fetch failed (${res.status})`);
  }
  const data = (await res.json()) as { prices: number[][] };
  return data.prices;
}
