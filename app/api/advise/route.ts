import { NextResponse } from "next/server";
import type { AdvisorResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

const SYSTEM_PROMPT = `You are the AI advisor inside a crypto PAPER trading app (simulated money, educational project). You analyze the user's portfolio, live market snapshot, and their strategy bots' latest signals, then give clear, level-headed suggestions.

Rules:
- This is a simulation; still, model good risk management (position sizing, no all-in bets, respect trends).
- Be specific and reference the data you were given (prices, 24h moves, RSI/SMA signals, P&L).
- It is fine to recommend doing nothing.
- Respond with ONLY valid JSON matching exactly this schema, no markdown fences:
{
  "assessment": "2-3 sentence overall read of the portfolio and market",
  "suggestions": [
    { "coinId": "<coingecko id from the snapshot>", "action": "buy" | "sell" | "hold", "sizeUsd": <number, omit for hold>, "confidence": "low" | "medium" | "high", "rationale": "1-2 sentences" }
  ],
  "tuning": [
    { "botLabel": "<coin symbol + strategy name>", "suggestion": "concrete parameter or configuration change and why" }
  ],
  "riskNotes": "1-2 sentences on the main risks right now"
}
- 1 to 4 suggestions, 0 to 2 tuning entries. sizeUsd must not exceed available cash for buys.`;

export async function POST(request: Request) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "no_key" }, { status: 503 });
  }

  let snapshot: unknown;
  try {
    snapshot = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const model = process.env.ADVISOR_MODEL || "claude-sonnet-5";

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
        max_tokens: 1500,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: "user",
            content: `Current snapshot (JSON):\n${JSON.stringify(snapshot, null, 2)}\n\nGive your advice as specified.`,
          },
        ],
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      return NextResponse.json(
        { error: `Anthropic API error (${res.status}): ${body.slice(0, 300)}` },
        { status: 502 }
      );
    }

    const data = (await res.json()) as {
      content: Array<{ type: string; text?: string }>;
    };
    const text =
      data.content?.find((b) => b.type === "text")?.text?.trim() ?? "";

    // Be forgiving about accidental code fences.
    const jsonText = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    const parsed = JSON.parse(jsonText) as AdvisorResponse;

    return NextResponse.json({
      advice: {
        assessment: String(parsed.assessment ?? ""),
        suggestions: Array.isArray(parsed.suggestions) ? parsed.suggestions : [],
        tuning: Array.isArray(parsed.tuning) ? parsed.tuning : [],
        riskNotes: String(parsed.riskNotes ?? ""),
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Advisor failed: ${message}` },
      { status: 502 }
    );
  }
}
