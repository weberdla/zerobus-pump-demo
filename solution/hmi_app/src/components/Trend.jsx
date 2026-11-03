import { useEffect, useRef, useState } from "react";
import { COLORS, fmt } from "../severity.js";

const L = 34, R = 10, T = 12, B = 22;
const WINDOW_MS = 10 * 60 * 1000;

// Draws in real pixels at whatever size the tab gives it, so text stays the same size as the plot grows.
function usePlotSize() {
  const ref = useRef(null);
  const [size, setSize] = useState({ W: 420, H: 140 });
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ W: Math.round(width), H: Math.round(height) });
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, size];
}

export default function Trend({ points, field, label, unit, limits, color, now, decimals = 1 }) {
  const [plotRef, { W, H }] = usePlotSize();
  const { min, max } = limits;
  const t0 = now - WINDOW_MS;
  const x = (t) => L + ((t - t0) / WINDOW_MS) * (W - L - R);
  const y = (v) => T + (1 - (Math.min(max, Math.max(min, v)) - min) / (max - min)) * (H - T - B);
  const data = points
    .filter((p) => p[field] != null && Date.parse(p.ts) >= t0)
    .map((p) => [x(Date.parse(p.ts)), y(p[field])]);
  const last = points.length ? points[points.length - 1][field] : null;
  const limitLines = [
    ["warning", limits.warning],
    ["alarm", limits.alarm],
  ].filter(([, value]) => value != null);

  return (
    <div className="trend">
      <div className="trend-head">
        <span>{label}</span>
        <span className="trend-last" style={{ color }}>
          {fmt(last, decimals)} {unit}
        </span>
      </div>
      <div className="trend-plot" ref={plotRef}>
      <svg viewBox={`0 0 ${W} ${H}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={L} x2={W - R} y1={T + f * (H - T - B)} y2={T + f * (H - T - B)} className="grid" />
        ))}
        <text x={L - 6} y={T + 4} className="axis" textAnchor="end">{max}</text>
        <text x={L - 6} y={H - B + 4} className="axis" textAnchor="end">{min}</text>
        <text x={L} y={H - 6} className="axis">−10 min</text>
        <text x={(L + W - R) / 2} y={H - 6} className="axis" textAnchor="middle">−5 min</text>
        <text x={W - R} y={H - 6} className="axis" textAnchor="end">now</text>
        {limitLines.map(([kind, value]) => (
          <g key={kind}>
            <line x1={L} x2={W - R} y1={y(value)} y2={y(value)} className="limit" style={{ stroke: COLORS[kind] }} />
            <text x={W - R - 4} y={y(value) - 4} className="limit-label" textAnchor="end" style={{ fill: COLORS[kind] }}>
              {kind === "alarm" ? "HH" : "H"} {value}
            </text>
          </g>
        ))}
        {data.length > 1 && (
          <polyline points={data.map((p) => p.join(",")).join(" ")} className="trend-line" style={{ stroke: color }} />
        )}
        {data.length > 0 && <circle cx={data[data.length - 1][0]} cy={data[data.length - 1][1]} r={3.5} style={{ fill: color }} />}
        {data.length === 0 && (
          <text x={(L + W - R) / 2} y={H / 2} className="axis" textAnchor="middle">No readings in the last 10 minutes</text>
        )}
      </svg>
      </div>
    </div>
  );
}
