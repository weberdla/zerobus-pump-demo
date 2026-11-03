import { COLORS, clamp, fmt, stateFor } from "../severity.js";

const CX = 70, CY = 70, R = 54, START = 150, SWEEP = 240;

const point = (deg) => [CX + R * Math.cos((deg * Math.PI) / 180), CY + R * Math.sin((deg * Math.PI) / 180)];

function arc(from, to) {
  const [x0, y0] = point(from);
  const [x1, y1] = point(to);
  return `M${x0} ${y0} A${R} ${R} 0 ${to - from > 180 ? 1 : 0} 1 ${x1} ${y1}`;
}

// Colored bands: normal / warning / alarm, on the high side or the low side of the scale.
function bands({ min, max, warning, alarm, low_warning, low_alarm }) {
  if (warning != null) return [[min, warning, "normal"], [warning, alarm, "warning"], [alarm, max, "alarm"]];
  if (low_warning != null) return [[min, low_alarm, "alarm"], [low_alarm, low_warning, "warning"], [low_warning, max, "normal"]];
  return [[min, max, "normal"]];
}

export default function Gauge({ label, tag, unit, value, limits, decimals = 1 }) {
  const { min, max } = limits;
  const angle = (v) => START + SWEEP * clamp((v - min) / (max - min), 0, 1);
  const state = stateFor(value, limits);
  const rotation = (value == null ? START : angle(value)) - 270;

  return (
    <div className={`gauge ${state}`}>
      <svg viewBox="0 0 140 122">
        <path d={arc(START, START + SWEEP)} className="gauge-track" />
        {bands(limits).map(([from, to, band]) => (
          <path key={band + from} d={arc(angle(from), angle(to))} className="gauge-band" style={{ stroke: COLORS[band] }} />
        ))}
        <g className="gauge-needle" style={{ transform: `rotate(${rotation}deg)`, transformOrigin: `${CX}px ${CY}px` }}>
          <line x1={CX} y1={CY + 8} x2={CX} y2={CY - R + 10} />
        </g>
        <circle cx={CX} cy={CY} r={5} className="gauge-hub" />
        <text x={CX} y={CY + 30} className="gauge-value" style={{ fill: state === "normal" ? "#e6f1f5" : COLORS[state] }}>
          {fmt(value, decimals)}
        </text>
        <text x={CX} y={CY + 46} className="gauge-unit">{unit}</text>
      </svg>
      <div className="gauge-label">
        {label} <span>{tag}</span>
      </div>
    </div>
  );
}
