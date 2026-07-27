import Link from "next/link";
import ExperimentsLedger from "@/components/ExperimentsLedger";
import ForwardStats from "@/components/ForwardStats";
import NarratorPanel from "@/components/NarratorPanel";
import TipJarPanel from "@/components/TipJarPanel";

export const metadata = {
  title: "Research — Crypto Paper Trader",
  description:
    "Live strategy state, forward-paper track record, and the full experiment ledger — including every killed idea.",
};

export default function ResearchPage() {
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
            ← Dashboard
          </Link>
        </div>
      </header>

      <div className="grid">
        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>Live Strategy · Narrated</h2>
            </div>
            <div className="panel-body">
              <NarratorPanel />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Forward-Paper Track Record</h2>
            </div>
            <div className="panel-body">
              <ForwardStats />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Experiment Ledger — including the corpses</h2>
            </div>
            <div className="panel-body">
              <ExperimentsLedger />
            </div>
          </section>
        </div>

        <div className="col">
          <section className="panel">
            <div className="panel-head">
              <h2>⚡ Support the Experiment</h2>
            </div>
            <div className="panel-body">
              <TipJarPanel />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Method</h2>
            </div>
            <div className="panel-body">
              <div className="notice" style={{ lineHeight: 1.7 }}>
                Every strategy here survived (or died by) the same rules:
                benchmarked against buy-and-hold, costs always on, walk-forward
                validation, kill criteria written before testing, and — for
                machine-generated candidates — deflated Sharpe statistics that
                count every trial ever run. Live claims come only from the
                forward-paper ledger. Simulated money; nothing on this page is
                financial advice.
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
