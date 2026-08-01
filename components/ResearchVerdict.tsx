import Figure from "./Figure";

/**
 * The headline. Six nulls is the finding, so it goes at the top at full size
 * rather than being inferred from a wall of cards further down.
 *
 * Counts are stated the way the ledger states them, not derived from a regex:
 * EXP-002/003/004 is one ledger entry covering three pre-registered overlays,
 * so "entries" and "experiments" are genuinely different numbers and printing
 * either one alone would mislead.
 */
export default function ResearchVerdict() {
  return (
    <section className="verdict-band">
      <div className="verdict-lead">
        <h1>
          Six pre-registered experiments.
          <br />
          <span className="verdict-emph">Six honest nulls.</span>
        </h1>
        <p>
          Every kill criterion was written <em>before</em> the run. Every failed
          idea is still below, with its numbers. The one survivor — Donchian
          breakout with volatility targeting — is recorded as a{" "}
          <strong>candidate under forward paper trading</strong>, not a strategy
          that works, and it stays that way until the live record says otherwise.
        </p>
        <p className="verdict-sub">
          This page is the research programme&apos;s report card. It is designed
          to be read by someone checking whether the numbers can be trusted —
          so the failures are the default view, and nothing here is hidden
          behind a toggle.
        </p>
      </div>

      <div className="verdict-figures">
        <Figure
          label="Pre-registered experiments"
          value="6"
          noCi="exact count, EXP-001 → EXP-006"
          note="plus 3 automated search campaigns (LAB-001→003)"
        />
        <Figure
          label="Strategies claimed to work"
          value="0"
          noCi="exact count"
          note="the claim requires ≥3 months of forward paper first"
        />
        {/* No start date is asserted here. Whether the forward clock has
            started is a fact that lives in the archive, and this component
            renders on a site with no backend attached — see ForwardStats,
            which reports it from data or says it cannot. */}
        <Figure
          label="Candidates awaiting forward paper"
          value="1"
          noCi="exact count"
          note="Donchian + vol targeting — the only survivor of walk-forward testing"
        />
      </div>
    </section>
  );
}
