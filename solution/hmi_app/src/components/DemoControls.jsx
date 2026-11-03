import { useState } from "react";
import { mmss, stepStates } from "../demoStatus.js";

const FAULTS = [
  ["none", "Healthy", "Normal operation. No alarms."],
  ["bearing", "Bearing fault", "Vibration and bearing temperature climb as the bearing wears. Set when the first WARNING and ALARM appear:"],
  ["cavitation", "Cavitation", "Suction pressure falls and vapour bubbles form at the inlet. Set when the first WARNING appears; the ALARM follows at about 1.8x that time:"],
];

// Default minutes from the start of streaming to the first WARNING and ALARM, and the cavitation
// ALARM/WARNING time ratio. Keep in step with FAULT_TIMELINE_MIN and CAVITATION_ALARM_RATIO in
// solution/pump_simulator.py.
const DEFAULT_TIMES = { bearing: { warning: "7", alarm: "13" }, cavitation: { warning: "7.5" } };
const CAVITATION_ALARM_RATIO = 1.79;

const round1 = (n) => Math.round(n * 10) / 10;

// Warning and alarm minutes for a fault, from typed text or a run's parameters (null = default).
function timeline(fault, warning, alarm) {
  if (fault === "none") return { warning: null, alarm: null };
  const w = parseFloat(warning ?? DEFAULT_TIMES[fault].warning);
  const a = fault === "bearing" ? parseFloat(alarm ?? DEFAULT_TIMES.bearing.alarm) : round1(w * CAVITATION_ALARM_RATIO);
  return { warning: w, alarm: a };
}

function timelineProblems(fault, { warning, alarm }, minutes) {
  if (fault === "none") return {};
  if (!(warning > 0 && warning <= 60)) return { error: "Enter a warning time between 0.5 and 60 minutes." };
  if (fault === "bearing" && !(alarm > warning && alarm <= 60)) return { error: "The alarm must come after the warning, within 60 minutes." };
  if (warning >= minutes) return { note: `The warning comes after the demo ends. Make the demo longer than ${warning} min.` };
  if (alarm >= minutes) return { note: `The alarm comes after the demo ends at ${minutes} min.` };
  return {};
}

const STEP_LABELS = {
  create_bronze: "Create the bronze table",
  start_live_silver: "Start the live silver pipeline",
  stream_pump_data: "Stream pump data through Zerobus Ingest",
  stop_live_silver: "Stop the live silver pipeline",
};

const STEP_STATES = {
  pending: ["○", "Waiting"],
  starting: ["◔", "Starting"],
  running: ["◐", "Running"],
  done: ["●", "Done"],
  skipped: ["–", "Skipped"],
  cancelled: ["×", "Cancelled"],
  failed: ["×", "Failed"],
};

export default function DemoControls({ demo, status, busy, notice, onStart, onStop }) {
  const [fault, setFault] = useState("bearing");
  const [minutes, setMinutes] = useState(15);
  const [times, setTimes] = useState(DEFAULT_TIMES);
  const active = demo?.active;
  // While a demo runs, show its fault, duration, and timeline rather than the local selection.
  const shownFault = active && demo.fault ? demo.fault : fault;
  const shownMinutes = active && demo.minutes ? demo.minutes : minutes;
  const typed = times[shownFault] ?? {};
  const shownTimes = active ? timeline(shownFault, demo.warning_minutes, demo.alarm_minutes) : timeline(shownFault, typed.warning, typed.alarm);
  const problems = active ? {} : timelineProblems(fault, shownTimes, minutes);
  const setTime = (key, value) => setTimes({ ...times, [fault]: { ...times[fault], [key]: value } });
  const timeInput = (key) => (
    <span className="time-input">
      <input type="number" min="0.5" max="60" step="0.5" disabled={active || busy}
             value={active ? shownTimes[key] : typed[key]} onChange={(e) => setTime(key, e.target.value)} />
      min
    </span>
  );
  const steps = stepStates(demo, status);

  return (
    <>
      <section className="panel controls">
        <div className="panel-title">Demo control</div>
        <div className="field-label">Fault</div>
        <div className="segmented">
          {FAULTS.map(([value, label]) => (
            <button key={value} className={shownFault === value ? "selected" : ""} disabled={active || busy} onClick={() => setFault(value)}>
              {label}
            </button>
          ))}
        </div>
        <p className="fault-help">{FAULTS.find(([value]) => value === shownFault)?.[2]}</p>
        {shownFault !== "none" && (
          <div className="timeline-row">
            <label>Warning at {timeInput("warning")}</label>
            {shownFault === "bearing" ? (
              <label>Alarm at {timeInput("alarm")}</label>
            ) : (
              <span className="derived">Alarm at about <b>{Number.isFinite(shownTimes.alarm) ? shownTimes.alarm : "--"}</b> min</span>
            )}
          </div>
        )}
        {shownFault !== "none" && (
          <p className={`timeline-note ${problems.error ? "error" : problems.note ? "warn" : ""}`}>
            {problems.error ?? problems.note ?? "Minutes after streaming starts, about 30 s after you click Start. The screen shows them about 15 s later."}
          </p>
        )}
        <div className="control-row">
          <label>
            Duration
            <select value={shownMinutes} disabled={active || busy} onChange={(e) => setMinutes(Number(e.target.value))}>
              {[...new Set([5, 10, 15, 20, 30, shownMinutes])].sort((a, b) => a - b).map((m) => (
                <option key={m} value={m}>{m} min</option>
              ))}
            </select>
          </label>
          <button className="start" disabled={active || busy || Boolean(problems.error)}
                  onClick={() => onStart(fault, minutes, shownTimes.warning, fault === "bearing" ? shownTimes.alarm : null)}>
            ▶ Start demo
          </button>
          <button className="stop" disabled={!active || busy} onClick={onStop}>■ Stop</button>
        </div>
        <p className="muted small">
          Start runs the <code>zerobus_pump_demo</code> job. When the stream ends, or you click Stop, the job shuts
          down the live silver pipeline, so nothing keeps running.
        </p>
      </section>

      <section className={`panel run-panel ${status.tone}`}>
        <div className="panel-title">Run status</div>
        <div className="run-headline">
          <span className="dot" />
          {status.headline}
          {active && demo.fault && (
            <span className="muted run-params">
              {FAULTS.find(([value]) => value === demo.fault)?.[1] ?? demo.fault} · {demo.minutes} min
              {demo.fault !== "none" && ` · warning ${shownTimes.warning} min · alarm ${shownTimes.alarm} min`}
            </span>
          )}
        </div>
        <p className="run-detail">{status.detail}</p>
        {status.progress && (
          <div className="progress">
            <div className="progress-bar" style={{ width: `${status.progress.frac * 100}%` }} />
            <span>{mmss(status.progress.left)} left</span>
          </div>
        )}
        {steps.length > 0 && (
          <ol className="steps">
            {steps.map((step) => {
              const [icon, label] = STEP_STATES[step.state] ?? ["?", step.state];
              return (
                <li key={step.key} className={step.state}>
                  <span className="step-icon">{icon}</span>
                  <span className="step-name">{STEP_LABELS[step.key] ?? step.key}</span>
                  <span className="step-state">{label}</span>
                </li>
              );
            })}
          </ol>
        )}
        {(active ? demo.run_url : demo?.last_run?.run_url) && (
          <a className="run-link" href={active ? demo.run_url : demo.last_run.run_url} target="_blank" rel="noreferrer">
            Open the {active ? "" : "last "}job run ↗
          </a>
        )}
        {notice && <div className="notice">{notice}</div>}
      </section>
    </>
  );
}
