import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** Serves the experiments ledger (research/experiments.md) as raw markdown. */
export async function GET() {
  try {
    const file = path.join(process.cwd(), "research", "experiments.md");
    const text = await fs.readFile(file, "utf-8");
    return NextResponse.json({ markdown: text });
  } catch {
    return NextResponse.json({ error: "ledger not found" }, { status: 404 });
  }
}
