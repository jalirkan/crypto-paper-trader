"use client";

import { useEffect, useRef } from "react";
import type { EquityPoint } from "@/lib/types";

interface Props {
  points: EquityPoint[];
  baseline: number; // starting cash — colors the line green/red relative to it
  height?: number;
}

/** Dependency-free canvas line chart with gradient fill. */
export default function EquityChart({ points, baseline, height = 160 }: Props) {
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

      if (points.length < 2) return;

      const values = points.map((p) => p.value);
      let min = Math.min(...values, baseline);
      let max = Math.max(...values, baseline);
      if (max - min < 1e-9) {
        min -= 1;
        max += 1;
      }
      const pad = (max - min) * 0.12;
      min -= pad;
      max += pad;

      const px = (i: number) => (i / (points.length - 1)) * (w - 4) + 2;
      const py = (v: number) => h - ((v - min) / (max - min)) * (h - 8) - 4;

      const lastValue = values[values.length - 1];
      const up = lastValue >= baseline;
      const lineColor = up ? "#22c55e" : "#ef4444";

      // Baseline (starting cash) dashed line
      ctx.strokeStyle = "rgba(139, 152, 169, 0.35)";
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, py(baseline));
      ctx.lineTo(w, py(baseline));
      ctx.stroke();
      ctx.setLineDash([]);

      // Gradient fill
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, up ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.beginPath();
      ctx.moveTo(px(0), py(values[0]));
      for (let i = 1; i < points.length; i++) ctx.lineTo(px(i), py(values[i]));
      ctx.lineTo(px(points.length - 1), h);
      ctx.lineTo(px(0), h);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Line
      ctx.beginPath();
      ctx.moveTo(px(0), py(values[0]));
      for (let i = 1; i < points.length; i++) ctx.lineTo(px(i), py(values[i]));
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.stroke();

      // Last point dot
      ctx.beginPath();
      ctx.arc(px(points.length - 1), py(lastValue), 3, 0, Math.PI * 2);
      ctx.fillStyle = lineColor;
      ctx.fill();
    }

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [points, baseline, height]);

  if (points.length < 2) {
    return (
      <div className="empty" style={{ height }}>
        Equity curve appears here once prices start streaming in.
      </div>
    );
  }

  return (
    <div ref={wrapRef} style={{ width: "100%" }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
