import Link from "next/link";
import ExperimentsLedger from "@/components/ExperimentsLedger";
import ForwardStats from "@/components/ForwardStats";
import NarratorPanel from "@/components/NarratorPanel";
import ResearchVerdict from "@/components/ResearchVerdict";
import TipJarPanel from "@/components/TipJarPanel";
import { readLedger } from "@/lib/ledger-server";

export const metadata = {
  title: "Research — Crypto Paper Trader",
  description:
    "Six pre-registered experiments, six honest nulls. The full ledger, including every killed idea, with intervals and sample sizes attached.",
};

export default async function ResearchPage() {
  // Read server-side: the ledger is the one part of this page that needs no
  // backend service, so it renders into the HTML rather than arriving over a
  // fetch that can fail on a site with nothing hosted behind it.
  const entries = await readLedger();

  return (
    <div className="container">
      <header className="app-header">
        <div className="app-title">
          <div className="logo">🔬</div>
          Research &amp; Track Record
          <span className="tag">Simulated</span>
        </div>
        <div className="header-meta">
          <Link className="btn sm ghost" href="/">
            ← Paper-trading dashboard
          </Link>
        </div>
      </header>

      <ResearchVerdict />

      <div className="grid">
        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>The ledger — every experiment, including the corpses</h2>
              {/* "entries" not "experiments": EXP-002/003/004 is a single
                  entry covering three pre-registered overlays. */}
              <span className="faint num">{entries.length} ledger entries</span>
            </div>
            <div className="panel-body">
              <ExperimentsLedger entries={entries} />
            </div>
          </section>
        </div>

        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>Forward-paper record</h2>
            </div>
            <div className="panel-body">
              <ForwardStats />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Today&apos;s position</h2>
            </div>
            <div className="panel-body">
              <NarratorPanel />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Method</h2>
            </div>
            <div className="panel-body">
              <div className="method">
                <p>
                  Every strategy here survived — or died by — the same rules:
                  benchmarked against buy-and-hold and flat cash, costs always
                  on (10 bps fee + 5 bps slippage per side), time-ordered
                  walk-forward validation with no shuffling, and kill criteria
                  written before the run rather than after seeing the result.
                </p>
                <p>
                  Machine-generated candidates face a harder bar still:
                  deflated-Sharpe statistics that count <em>every</em> trial
                  ever run, plus a sealed holdout. Across three search
                  campaigns, 483 candidates were evaluated (N = 317 cumulative
                  in LAB-001/002, 166 in LAB-003) and not one survived it.
                </p>
                <p className="faint">
                  Simulated money throughout. Nothing on this page is financial
                  advice, and no strategy here is claimed to work.
                </p>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>⚡ Support the experiment</h2>
            </div>
            <div className="panel-body">
              <TipJarPanel />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
