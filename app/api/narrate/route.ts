import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const SIGNALS_URL = process.env.SIGNALS_URL || "http://127.0.0.1:8091";

const SYSTEM_PROMPT = `You are the narrator of a public crypto PAPER-trading experiment (simulated money, real strategy, real data). Given the live strategy state, write the day's briefing.

Rules:
- 130–190 words, plain confident language, no hype, no emojis, no financial advice.
- Explain WHAT the strategy holds and WHY in breakout terms a newcomer can follow: Donchian goes long when price breaks above its trailing N-day high, exits on the trailing low. Reference the actual entry/exit levels, dates and days-in-state from the data.
- If forward-paper stats exist, weave in one honest sentence about the live track record vs buy-and-hold.
- This strategy was the only survivor of walk-forward testing (MA-cross and momentum variants failed out-of-sample) — mention this only if it flows naturally.
- End with what would change the current stance (the specific level that flips it).
Output plain text only, no headers or markdown.`;

export async function GET() {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "no_key" }, { status: 503 });
  }

  let state: unknown;
  try {
    const [sigRes, fwdRes] = await Promise.all([
      fetch(`${SIGNALS_URL}/api/signals`, { cache: "no-store" }),
      fetch(`${SIGNALS_URL}/api/forward`, { cache: "no-store" }),
    ]);
    if (!sigRes.ok) throw new Error("service down");
    state = { signals: await sigRes.json(), forward: fwdRes.ok ? await fwdRes.json() : null };
  } catch {
    return NextResponse.json({ error: "signal_service_down" }, { status: 503 });
  }

  const model = process.env.NARRATOR_MODEL || "claude-sonnet-5";
  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model,
        max_tokens: 500,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: "user",
            content: `Live strategy state (JSON):\n${JSON.stringify(state, null, 1)}\n\nWrite today's briefing.`,
          },
        ],
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      return NextResponse.json(
        { error: `Anthropic API error (${res.status}): ${body.slice(0, 200)}` },
        { status: 502 }
      );
    }
    const data = (await res.json()) as { content: Array<{ type: string; text?: string }> };
    const narration = data.content?.find((b) => b.type === "text")?.text?.trim() ?? "";
    return NextResponse.json({ narration, model, at: Date.now() });
  } catch (err) {
    const message = err instanceof Error ? err.message : "unknown";
    return NextResponse.json({ error: `Narrator failed: ${message}` }, { status: 502 });
  }
}
