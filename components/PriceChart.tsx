"use client";

import { useEffect, useRef, useState } from "react";
import { fetchHistory } from "@/lib/market";

interface Props {
  coinId: string;
  days?: 1 | 7 | 30 | 90;
  height?: number;
}

/** Small canvas price chart for a single coin. */
export default function PriceChart({ coinId, days = 7, height = 120 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [series, setSeries] = useState<number[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSeries(null);
    setFailed(false);
    fetchHistory(coinId, days)
      .then((prices) => {
        if (!cancelled) setSeries(prices.map((p) => p[1]));
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [coinId, days]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || !series || series.length < 2) return;

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

    let min = Math.min(...series);
    let max = Math.max(...series);
    if (max - min < 1e-9) {
      min -= 1;
      max += 1;
    }

    const px = (i: number) => (i / (series.length - 1)) * (w - 4) + 2;
    const py = (v: number) => h - ((v - min) / (max - min)) * (h - 8) - 4;

    const up = series[series.length - 1] >= series[0];
    const color = up ? "#22c55e" : "#ef4444";

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, up ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.beginPath();
    ctx.moveTo(px(0), py(series[0]));
    for (let i = 1; i < series.length; i++) ctx.lineTo(px(i), py(series[i]));
    ctx.lineTo(px(series.length - 1), h);
    ctx.lineTo(px(0), h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    ctx.moveTo(px(0), py(series[0]));
    for (let i = 1; i < series.length; i++) ctx.lineTo(px(i), py(series[i]));
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.stroke();
  }, [series, height]);

  if (failed) {
    return (
      <div className="empty" style={{ height }}>
        Chart unavailable (rate limited — try again shortly).
      </div>
    );
  }

  if (!series) {
    return (
      <div className="empty" style={{ height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span className="spin" />
      </div>
    );
  }

  return (
    <div ref={wrapRef} style={{ width: "100%" }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
