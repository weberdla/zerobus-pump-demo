import { COLORS, clamp, fmt, highState, lowState, worst } from "../severity.js";

const VANES = [0, 60, 120, 180, 240, 300];
// Cavitation vapour bubbles at the suction inlet and the impeller eye.
const BUBBLES = [
  [236, 322, 0], [252, 338, 0.3], [268, 318, 0.6], [226, 342, 0.9], [284, 330, 1.2], [246, 314, 1.5],
  [318, 322, 0.15], [330, 340, 0.45], [324, 312, 0.75],
];

// ISA-style instrument bubble with a leader line to the process and a live value box.
function Instrument({ x, y, tag, to, label, value, unit, state = "normal", box }) {
  const [letters, number] = tag.split("-");
  return (
    <g className="instrument">
      <line x1={x} y1={to[0]} x2={x} y2={to[1]} className="signal" />
      <circle cx={x} cy={y} r={22} className="bubble-ring" />
      <line x1={x - 22} y1={y} x2={x + 22} y2={y} className="bubble-split" />
      <text x={x} y={y - 6} className="tag-letters">{letters}</text>
      <text x={x} y={y + 15} className="tag-number">{number}</text>
      <g transform={`translate(${box[0]} ${box[1]})`}>
        <rect width={140} height={46} rx={6} className="value-box" style={{ stroke: COLORS[state] }} />
        <text x={10} y={16} className="value-label">{label}</text>
        <text x={10} y={37} className="value-number" style={{ fill: state === "normal" ? "#e6f1f5" : COLORS[state] }}>
          {value}
          <tspan className="value-unit"> {unit}</tspan>
        </text>
      </g>
    </g>
  );
}

export default function PumpGraphic({ tags, limits }) {
  const v = (name) => tags[name]?.value ?? null;
  const running = (v("Running") ?? 0) >= 0.5;
  const speed = v("MotorSpeed") ?? 0;
  const flow = v("FlowRate") ?? 0;
  const vibration = v("Vibration") ?? 0;
  const bearingTemp = v("BearingTemp") ?? 0;
  const suction = v("SuctionPressure");

  const vibState = highState(vibration, limits.Vibration);
  const tempState = highState(bearingTemp, limits.BearingTemp);
  const bearingState = worst(vibState, tempState);
  const suctionState = running ? lowState(suction, limits.SuctionPressure) : "normal";

  const spinning = running && speed > 60;
  const spinSeconds = spinning ? Math.min(6, (0.9 * 1780) / speed) : 1;
  const flowing = flow > 2;
  const flowSeconds = flowing ? clamp((1.6 * 110) / flow, 0.5, 6) : 1;
  const shake = vibration > 3 ? clamp((vibration - 3) * 0.55, 0.3, 4) : 0;
  const heat = clamp((bearingTemp - 20) / 80, 0, 1);

  return (
    <svg viewBox="0 0 960 560" className="pump-graphic" role="img" aria-label="PUMP-101 process graphic">
      <defs>
        <linearGradient id="pipe-h" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3f515c" />
          <stop offset="0.5" stopColor="#1f2c34" />
          <stop offset="1" stopColor="#3f515c" />
        </linearGradient>
        <linearGradient id="pipe-v" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3f515c" />
          <stop offset="0.5" stopColor="#1f2c34" />
          <stop offset="1" stopColor="#3f515c" />
        </linearGradient>
        <radialGradient id="casing" cx="0.4" cy="0.35" r="0.75">
          <stop offset="0" stopColor="#4a5f6b" />
          <stop offset="1" stopColor="#1b272e" />
        </radialGradient>
        <linearGradient id="motor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3b4f5a" />
          <stop offset="1" stopColor="#1a252c" />
        </linearGradient>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="12" />
        </filter>
      </defs>

      {/* Process piping with animated flow */}
      <text x={34} y={376} className="process-label">FROM TANK T-100 →</text>
      <text x={926} y={152} className="process-label" textAnchor="end">TO DISCHARGE HEADER →</text>
      <rect x={30} y={308} width={236} height={44} rx={4} fill="url(#pipe-h)" />
      <rect x={252} y={298} width={14} height={64} rx={2} className="flange" />
      <rect x={318} y={88} width={612} height={44} rx={4} fill="url(#pipe-h)" />
      <rect x={318} y={110} width={44} height={150} fill="url(#pipe-v)" />
      <rect x={308} y={232} width={64} height={14} rx={2} className="flange" />
      <path d="M38 330 H250" className={`flow ${flowing ? "" : "paused"}`} style={{ animationDuration: `${flowSeconds}s` }} />
      <path d="M340 240 V110 H924" className={`flow ${flowing ? "" : "paused"}`} style={{ animationDuration: `${flowSeconds}s` }} />

      {/* Pump, bearing housing, and motor shake together when vibration is high */}
      <g className={shake ? "shake" : ""} style={{ "--amp": `${shake}px` }}>
        <rect x={250} y={440} width={660} height={18} rx={3} className="skid" />
        <rect x={322} y={410} width={76} height={32} rx={3} className="skid" />
        <circle cx={360} cy={330} r={104} fill="url(#casing)" className="casing" />
        <circle cx={360} cy={330} r={88} className="casing-window" />
        <g transform="translate(360 330)">
          <g className={`spin ${spinning ? "" : "paused"}`} style={{ animationDuration: `${spinSeconds}s` }}>
            <circle r={80} className="shroud" />
            {VANES.map((angle) => (
              <path key={angle} d="M18 4 C40 2 60 -12 76 -34" transform={`rotate(${angle})`} className="vane" />
            ))}
            <circle r={17} className="hub" />
            <circle r={6} className="hub-bore" />
          </g>
        </g>
        <text x={360} y={460} className="equip-label">P-101</text>

        {suctionState !== "normal" &&
          BUBBLES.map(([cx, cy, delay], i) => (
            <circle key={i} cx={cx} cy={cy} r={5} className="cavitation" style={{ animationDelay: `${delay}s` }} />
          ))}

        <rect x={462} y={322} width={170} height={16} rx={3} className="shaft" />
        {bearingState !== "normal" && (
          <rect x={456} y={274} width={128} height={112} rx={18} filter="url(#glow)"
                className={`bearing-glow ${bearingState}`} style={{ fill: COLORS[bearingState] }} />
        )}
        <rect x={470} y={288} width={100} height={84} rx={10} className="bearing" style={{ stroke: COLORS[bearingState] }} />
        <text x={520} y={318} className="bearing-label">DE BEARING</text>
        <rect x={484} y={334} width={72} height={8} rx={4} className="heat-track" />
        <rect x={484} y={334} width={72 * heat} height={8} rx={4} style={{ fill: COLORS[tempState] }} />
        <text x={520} y={360} className="bearing-temp" style={{ fill: COLORS[tempState] }}>{fmt(bearingTemp, 1)} °C</text>
        {vibration > 2.6 &&
          [0, 1, 2].map((i) => (
            <g key={i} className={`vib-wave ${vibState}`} style={{ animationDelay: `${i * 0.18}s`, stroke: COLORS[vibState] }}>
              <path d={`M${488 + i * 4} ${276 - i * 9} q32 ${-10 - i * 2} 64 0`} />
              <path d={`M${488 + i * 4} ${384 + i * 9} q32 ${10 + i * 2} 64 0`} />
            </g>
          ))}

        <rect x={600} y={304} width={30} height={52} rx={5} className="coupling" />
        <rect x={650} y={405} width={40} height={37} rx={3} className="skid" />
        <rect x={800} y={405} width={40} height={37} rx={3} className="skid" />
        <rect x={630} y={255} width={230} height={150} rx={16} fill="url(#motor)" className="motor" />
        {Array.from({ length: 8 }, (_, i) => (
          <line key={i} x1={654 + i * 26} y1={272} x2={654 + i * 26} y2={388} className="fin" />
        ))}
        <rect x={860} y={274} width={34} height={112} rx={10} className="fan-cover" />
        <text x={745} y={338} className="motor-label">M-101</text>
        <circle cx={838} cy={274} r={7} className={`run-light ${running ? "on" : ""}`} />
      </g>

      {/* Field instruments */}
      <Instrument x={150} y={240} tag="PI-101" to={[262, 308]} box={[166, 217]} label="SUCTION PRESSURE"
                  value={fmt(suction, 2)} unit="bar" state={suctionState} />
      <Instrument x={470} y={42} tag="PI-102" to={[64, 88]} box={[500, 19]} label="DISCHARGE PRESSURE"
                  value={fmt(v("DischargePressure"), 2)} unit="bar" />
      <Instrument x={760} y={42} tag="FI-101" to={[64, 88]} box={[790, 19]} label="FLOW"
                  value={fmt(flow, 1)} unit="m³/h" />
      <Instrument x={520} y={212} tag="TI-101" to={[234, 288]} box={[550, 189]} label="BEARING TEMP"
                  value={fmt(bearingTemp, 1)} unit="°C" state={tempState} />
      <Instrument x={720} y={204} tag="II-101" to={[226, 255]} box={[750, 181]} label="MOTOR CURRENT"
                  value={fmt(v("MotorCurrent"), 1)} unit="A" />
      <Instrument x={520} y={506} tag="VI-101" to={[484, 372]} box={[550, 483]} label="VIBRATION"
                  value={fmt(vibration, 2)} unit="mm/s" state={vibState} />
      <Instrument x={720} y={506} tag="SI-101" to={[484, 405]} box={[750, 483]} label="SPEED"
                  value={fmt(speed, 0)} unit="rpm" />
    </svg>
  );
}
