/**
 * Parser for research/experiments.md.
 *
 * The ledger is the source of truth and it is hand-written markdown, so this
 * parses defensively: it strips the fenced format template out of the header
 * (which otherwise renders as a real experiment called "EXP-NNN"), splits on
 * entry headings, and pulls the `Label:` fields into structured form.
 *
 * Verdict classification is deliberately mechanical — it reports which of
 * KEEP/KILL the ledger's own Verdict field contains, and nothing cleverer.
 * Judging "did an edge survive" from prose is exactly the kind of inference
 * this project doesn't let itself make silently.
 */

export type Outcome = "kill" | "keep" | "mixed" | "null";

export interface LedgerEntry {
  /** e.g. "EXP-006" or "EXP-002/003/004" */
  id: string;
  /** ISO date as written in the heading, or "" if absent */
  date: string;
  /** short name after the second separator */
  name: string;
  /** full heading text, unmodified */
  heading: string;
  /** ordered Label -> text, e.g. Hypothesis, Config, Result, Verdict */
  fields: Array<{ label: string; text: string }>;
  outcome: Outcome;
  /** the Verdict field text, or "" — surfaced even when collapsed */
  verdict: string;
  /** the Result field text, or "" */
  result: string;
}

/** Remove ``` fenced blocks so the header's format template isn't parsed. */
function stripFences(md: string): string {
  return md.replace(/^```[\s\S]*?^```/gm, "");
}

const HEADING_RE = /^(\S+)\s+·\s+(\d{4}-\d{2}-\d{2})\s+·\s+([\s\S]+)$/;
// Field labels sit at column 0; continuation lines are indented, so anchoring
// to the line start is what separates a field from prose containing a colon.
const FIELD_RE = /^([A-Z][A-Za-z ]{1,14}):[ \t]{1,}(.*)$/;

function classify(verdict: string): Outcome {
  const hasKill = /\bKILL/.test(verdict);
  const hasKeep = /\bKEEP/.test(verdict);
  if (hasKill && hasKeep) return "mixed";
  if (hasKill) return "kill";
  if (hasKeep) return "keep";
  return "null";
}

export function parseLedger(markdown: string): LedgerEntry[] {
  const parts = stripFences(markdown).split(/^## /m).slice(1);

  const entries = parts.map((part) => {
    const [headingRaw, ...bodyLines] = part.split("\n");
    const heading = headingRaw.trim();
    const m = HEADING_RE.exec(heading);

    const fields: Array<{ label: string; text: string }> = [];
    let current: { label: string; text: string } | null = null;

    for (const line of bodyLines) {
      const fm = FIELD_RE.exec(line);
      if (fm) {
        current = { label: fm[1].trim(), text: fm[2].trim() };
        fields.push(current);
      } else if (current) {
        const t = line.trim();
        current.text += t ? ` ${t}` : "\n";
      }
    }
    for (const f of fields) f.text = f.text.replace(/[ \t]+/g, " ").trim();

    const find = (label: string) =>
      fields.find((f) => f.label.toLowerCase() === label)?.text ?? "";
    const verdict = find("verdict");

    return {
      id: m ? m[1] : heading,
      date: m ? m[2] : "",
      name: m ? m[3].trim() : "",
      heading,
      fields,
      verdict,
      result: find("result"),
      outcome: classify(verdict),
    };
  });

  // Newest first. The file is not in chronological order; a ledger should be.
  return entries.sort((a, b) => (a.date === b.date ? 0 : a.date < b.date ? 1 : -1));
}

export interface LedgerTally {
  entries: number;
  kills: number;
  /** entries whose verdict retained something, whole or in part */
  retained: number;
}

export function tally(entries: LedgerEntry[]): LedgerTally {
  return {
    entries: entries.length,
    kills: entries.filter((e) => e.outcome === "kill" || e.outcome === "mixed").length,
    retained: entries.filter((e) => e.outcome === "keep" || e.outcome === "mixed").length,
  };
}

export const OUTCOME_LABEL: Record<Outcome, string> = {
  kill: "KILL",
  keep: "KEEP",
  mixed: "KILL + KEEP",
  null: "NULL",
};
