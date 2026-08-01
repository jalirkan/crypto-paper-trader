"use client";

import { useEffect, useRef } from "react";

interface Props {
  days: string[];
  strategy: number[];
  buyHold: number[];
  height?: number;
}

/**
 * Forward-paper equity against buy-and-hold. Dependency-free canvas, matching
 * EquityChart's approach.
 *
 * Both series are indexed to 1.0 on the first recorded day, so the chart shows
 * relative performance from a common start — which is the only comparison that
 * means anything here. The benchmark is drawn in a deliberately plain grey: it
 * is the thing to beat, not a second result, and colouring both lines invites
 * reading the pair as a horse race rather than a claim under test.
 *
 * No animation. A curve that draws itself in makes the reader wait to find out
 * what happened, which is the wrong instinct on this page.
 */
export default function ForwardCurve({ days, strategy, buyHold, height = 170 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    function draw() {
      if (!canvas || !wrap) return;
      const dpr = window.devicePixelRatio || 1;
      const w = wrap.clientWidth;
      const h = height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const n = Math.min(strategy.length, buyHold.length);
      if (n < 2) return;

      const all = [...strategy.slice(0, n), ...buyHold.slice(0, n), 1];
      let min = Math.min(...all);
      let max = Math.max(...all);
      if (max - min < 1e-9) {
        min -= 0.01;
        max += 0.01;
      }
      const pad = (max - min) * 0.15;
      min -= pad;
      max += pad;

      const left = 2;
      const right = w - 2;
      const px = (i: number) => left + (i / (n - 1)) * (right - left);
      const py = (v: number) => h - ((v - min) / (max - min)) * (h - 22) - 18;

      // The 1.0 line: break-even against the starting index.
      ctx.strokeStyle = "rgba(139, 152, 169, 0.28)";
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, py(1));
      ctx.lineTo(w, py(1));
      ctx.stroke();
      ctx.setLineDash([]);

      const line = (series: number[], color: string, width: number) => {
        ctx.beginPath();
        ctx.moveTo(px(0), py(series[0]));
        for (let i = 1; i < n; i++) ctx.lineTo(px(i), py(series[i]));
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.lineJoin = "round";
        ctx.stroke();
      };

      line(buyHold, "rgba(139, 152, 169, 0.75)", 1.5);
      line(strategy, "#3b82f6", 2);

      // End dot on the strategy only — it is the series under test.
      ctx.beginPath();
      ctx.arc(px(n - 1), py(strategy[n - 1]), 3, 0, Math.PI * 2);
      ctx.fillStyle = "#3b82f6";
      ctx.fill();

      // Date bounds, so the horizontal axis is never mistaken for a long run.
      ctx.fillStyle = "rgba(139, 152, 169, 0.7)";
      ctx.font = "10px ui-monospace, Consolas, monospace";
      ctx.textBaseline = "bottom";
      if (days.length >= 2) {
        ctx.textAlign = "left";
        ctx.fillText(days[0], left, h - 2);
        ctx.textAlign = "right";
        ctx.fillText(days[days.length - 1], right, h - 2);
      }
    }

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [days, strategy, buyHold, height]);

  if (strategy.length < 2 || buyHold.length < 2) return null;

  return (
    <div className="fwd-curve">
      <div className="fwd-legend">
        <span className="fwd-key">
          <i className="swatch strat" /> strategy
        </span>
        <span className="fwd-key">
          <i className="swatch bh" /> buy &amp; hold
        </span>
        <span className="fwd-key faint">both indexed to 1.00 at the first recorded day</span>
      </div>
      <div ref={wrapRef} style={{ width: "100%" }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
