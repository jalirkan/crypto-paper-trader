import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const SIGNALS_URL = process.env.SIGNALS_URL || "http://127.0.0.1:8091";

/** Proxies the Python signal service so the client never needs its address. */
export async function GET() {
  try {
    const [sigRes, fwdRes] = await Promise.all([
      fetch(`${SIGNALS_URL}/api/signals`, { cache: "no-store" }),
      fetch(`${SIGNALS_URL}/api/forward`, { cache: "no-store" }),
    ]);
    if (!sigRes.ok) throw new Error(`signal service responded ${sigRes.status}`);
    const signals = await sigRes.json();
    const forward = fwdRes.ok ? await fwdRes.json() : null;
    return NextResponse.json({ ...signals, forward });
  } catch {
    return NextResponse.json(
      {
        error: "signal_service_down",
        hint: "Start it with: python -m research.signal_service",
      },
      { status: 503 }
    );
  }
}
