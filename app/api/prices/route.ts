import { NextResponse } from "next/server";
import { COINS } from "@/lib/coins";
import type { PriceMap } from "@/lib/types";

export const dynamic = "force-dynamic";

const CACHE_TTL_MS = 60_000;

let cache: { data: PriceMap; ts: number } | null = null;

interface GeckoMarket {
  id: string;
  current_price: number;
  price_change_percentage_24h: number | null;
  market_cap: number;
  total_volume: number;
}

/**
 * Proxies CoinGecko's /coins/markets endpoint with a 60s in-memory cache so the
 * client can poll freely without hitting upstream rate limits.
 */
export async function GET() {
  if (cache && Date.now() - cache.ts < CACHE_TTL_MS) {
    return NextResponse.json({ prices: cache.data, cached: true });
  }

  const ids = COINS.map((c) => c.id).join(",");
  const url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=${ids}&order=market_cap_desc&per_page=${COINS.length}&sparkline=false`;

  try {
    const res = await fetch(url, {
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`CoinGecko responded ${res.status}`);
    const markets = (await res.json()) as GeckoMarket[];

    const prices: PriceMap = {};
    const now = Date.now();
    for (const m of markets) {
      prices[m.id] = {
        price: m.current_price,
        change24h: m.price_change_percentage_24h ?? 0,
        marketCap: m.market_cap,
        volume24h: m.total_volume,
        updatedAt: now,
      };
    }

    cache = { data: prices, ts: now };
    return NextResponse.json({ prices, cached: false });
  } catch (err) {
    // Serve stale data if we have it — better than nothing during rate limits.
    if (cache) {
      return NextResponse.json({ prices: cache.data, cached: true, stale: true });
    }
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Failed to fetch prices: ${message}` },
      { status: 502 }
    );
  }
}
