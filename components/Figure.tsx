/**
 * A number that cannot be rendered bare.
 *
 * The research side of this project refuses to print a point estimate without
 * its interval — that discipline is what turned EXP-006 from "ETH passes at
 * 5.13%" into a kill. This component enforces the same rule in the type
 * system: every Figure must supply either a confidence interval or a written
 * reason there isn't one. There is no third option, so a bare percentage is a
 * compile error rather than an oversight.
 */

interface FigureBase {
  label: string;
  /** pre-formatted, e.g. "+4.67%" — formatting belongs to the caller */
  value: string;
  /** sample size, when the figure is an estimate from data */
  n?: number;
  /** unit shown next to n, e.g. "epochs", "events" */
  nUnit?: string;
  /** short clarifier under the figure */
  note?: string;
  tone?: "neutral" | "good" | "bad";
}

type FigureProps = FigureBase &
  (
    | { ci: string; noCi?: never }
    | { noCi: string; ci?: never }
  );

export default function Figure(props: FigureProps) {
  const { label, value, n, nUnit, note, tone = "neutral" } = props;
  const toneClass = tone === "good" ? "up" : tone === "bad" ? "down" : "";

  return (
    <div className="figure">
      <div className="figure-label">{label}</div>
      <div className={`figure-value num ${toneClass}`}>{value}</div>
      <div className="figure-ci num">
        {"ci" in props && props.ci ? (
          <>95% CI {props.ci}</>
        ) : (
          <span className="figure-noci">{props.noCi}</span>
        )}
      </div>
      {/* An exact count is its own population, so "n" is meaningless noise
          there. A missing n next to a real interval is a genuine gap and does
          get called out. */}
      <div className="figure-n">
        {n !== undefined ? (
          <>
            n = {n.toLocaleString("en-US")}
            {nUnit ? ` ${nUnit}` : ""}
          </>
        ) : "ci" in props && props.ci ? (
          <span className="figure-noci">sample size not reported</span>
        ) : null}
        {note ? (
          <span className="figure-note">
            {n !== undefined || ("ci" in props && props.ci) ? " · " : ""}
            {note}
          </span>
        ) : null}
      </div>
    </div>
  );
}
