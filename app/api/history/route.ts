import { NextResponse } from "next/server";
import { COIN_MAP } from "@/lib/coins";

export const dynamic = "force-dynamic";

const CACHE_TTL_MS = 5 * 60_000;

const cache = new Map<string, { prices: number[][]; ts: number }>();

/**
 * GET /api/history?coin=bitcoin&days=1
 * Proxies CoinGecko market_chart with a 5 min cache per (coin, days).
 * Returns { prices: [ [epochMs, price], ... ] } oldest → newest.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const coin = searchParams.get("coin") ?? "";
  const days = searchParams.get("days") ?? "1";

  if (!COIN_MAP[coin]) {
    return NextResponse.json({ error: "Unknown coin" }, { status: 400 });
  }
  if (!["1", "7", "30", "90"].includes(days)) {
    return NextResponse.json({ error: "days must be 1, 7, 30 or 90" }, { status: 400 });
  }

  const key = `${coin}:${days}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.ts < CACHE_TTL_MS) {
    return NextResponse.json({ prices: hit.prices, cached: true });
  }

  const url = `https://api.coingecko.com/api/v3/coins/${coin}/market_chart?vs_currency=usd&days=${days}`;

  try {
    const res = await fetch(url, {
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`CoinGecko responded ${res.status}`);
    const data = (await res.json()) as { prices: number[][] };
    cache.set(key, { prices: data.prices, ts: Date.now() });
    return NextResponse.json({ prices: data.prices, cached: false });
  } catch (err) {
    if (hit) {
      return NextResponse.json({ prices: hit.prices, cached: true, stale: true });
    }
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Failed to fetch history: ${message}` },
      { status: 502 }
    );
  }
}
