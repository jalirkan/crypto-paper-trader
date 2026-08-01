import { OUTCOME_LABEL, type LedgerEntry, type Outcome } from "@/lib/ledger";

/**
 * Renders research/experiments.md as structured entries — server-side, so the
 * ledger is in the HTML with no backend service and no client fetch.
 *
 * The design rule here: a collapsed entry must still say what happened. Hiding
 * a verdict behind a disclosure triangle is how a ledger of failures quietly
 * becomes a list of neutral-looking cards.
 */

/**
 * Nothing here is green.
 *
 * A green badge reads as "this one worked", and no entry in this ledger
 * supports that claim — every KEEP is either a retained *candidate* awaiting
 * forward paper or a retained *finding* about why something failed. Colouring
 * those like wins would overclaim in exactly the direction the whole project
 * is built to resist.
 */
const TONE: Record<Outcome, string> = {
  kill: "sell", // red
  mixed: "bot", // amber
  keep: "bot", // amber — a candidate, never a win
  null: "hold", // grey
};

const GIST_MAX = 150;

/**
 * The ledger is hand-written markdown and uses **bold**, *italic* and `code`
 * for emphasis — often on the load-bearing part of a finding ("**net APR ≥
 * 5%**", "*conditional on leveraged-long crowding*"). Rendering it as plain
 * text prints the asterisks and drops the emphasis the author intended, so
 * these three inline forms are converted. Nothing else is interpreted: this
 * is a deliberate whitelist, not a markdown engine.
 */
const INLINE_RE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;

function inline(text: string, keyPrefix: string) {
  return text.split(INLINE_RE).map((tok, i) => {
    const key = `${keyPrefix}-${i}`;
    if (tok.startsWith("**") && tok.endsWith("**")) {
      return <strong key={key}>{tok.slice(2, -2)}</strong>;
    }
    if (tok.startsWith("`") && tok.endsWith("`")) {
      return <code key={key}>{tok.slice(1, -1)}</code>;
    }
    if (tok.startsWith("*") && tok.endsWith("*") && tok.length > 2) {
      return <em key={key}>{tok.slice(1, -1)}</em>;
    }
    return <span key={key}>{tok}</span>;
  });
}

/** First sentence of the verdict — the summary shown while collapsed. */
function gist(verdict: string): string {
  if (!verdict) return "";
  const m = /^(.*?[.!])(\s|$)/.exec(verdict);
  const first = (m ? m[1] : verdict).trim();
  if (first.length <= GIST_MAX) return first;
  const cut = first.slice(0, GIST_MAX);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

function EntryCard({ entry, open }: { entry: LedgerEntry; open: boolean }) {
  return (
    <details className="exp-card" open={open}>
      <summary>
        <div className="exp-head">
          <span className={`badge ${TONE[entry.outcome]}`}>{OUTCOME_LABEL[entry.outcome]}</span>
          <span className="exp-id num">{entry.id}</span>
          <span className="exp-name">{entry.name || entry.heading}</span>
          <span className="exp-date num faint">{entry.date}</span>
        </div>
        {entry.verdict ? (
          <div className="exp-gist">{inline(gist(entry.verdict), `${entry.id}-gist`)}</div>
        ) : null}
      </summary>

      <dl className="exp-fields">
        {entry.fields.map((f) => (
          <div className="exp-field" key={f.label}>
            <dt>{f.label}</dt>
            <dd>
              {f.text.split("\n").map((para, i) =>
                para.trim() ? (
                  <p key={i}>{inline(para.trim(), `${entry.id}-${f.label}-${i}`)}</p>
                ) : null
              )}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export default function ExperimentsLedger({ entries }: { entries: LedgerEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="notice">
        The ledger file (<code>research/experiments.md</code>) could not be read.
        It is the source of truth for this page and is checked into the repo —
        this is a deployment fault, not an empty result.
      </div>
    );
  }

  return (
    <div className="exp-list">
      {entries.map((e, i) => (
        <EntryCard key={e.id + e.date} entry={e} open={i === 0} />
      ))}
    </div>
  );
}
