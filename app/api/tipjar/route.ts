import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const TIPS_URL = process.env.TIPS_URL || "http://127.0.0.1:8090";

/** Proxies the Lightning tip-jar service's public ledger. */
export async function GET() {
  try {
    const res = await fetch(`${TIPS_URL}/api/tips`, { cache: "no-store" });
    if (!res.ok) throw new Error(`tip jar responded ${res.status}`);
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ error: "tipjar_down" }, { status: 503 });
  }
}
