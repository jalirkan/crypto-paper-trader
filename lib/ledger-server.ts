import { promises as fs } from "fs";
import path from "path";
import { parseLedger, type LedgerEntry } from "./ledger";

/**
 * Reads research/experiments.md at request time on the server.
 *
 * Server-side on purpose: the ledger is the one part of this page that needs
 * no backend service, so it should render into the HTML rather than arrive
 * via a client fetch that can fail. next.config.mjs traces the file into the
 * deployment bundle (outputFileTracingIncludes) so this also works on Vercel.
 */
export async function readLedger(): Promise<LedgerEntry[]> {
  try {
    const file = path.join(process.cwd(), "research", "experiments.md");
    return parseLedger(await fs.readFile(file, "utf-8"));
  } catch {
    return [];
  }
}
