import { useState } from "react";
import { mmss, stepStates } from "../demoStatus.js";

const FAULTS = [
  ["none", "Healthy", "Normal operation. No alarms."],
  ["bearing", "Bearing fault", "Vibration and bearing temperature climb: WARNING at about 7 minutes, ALARM at about 13."],
  ["cavitation", "Cavitation", "Suction pressure falls and vapour bubbles form: WARNING at about 7-8 minutes, so run at least 10."],
];

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
  const active = demo?.active;
  // While a demo runs, show its fault and duration rather than the local selection.
  const shownFault = active && demo.fault ? demo.fault : fault;
  const shownMinutes = active && demo.minutes ? demo.minutes : minutes;
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
        <div className="control-row">
          <label>
            Duration
            <select value={shownMinutes} disabled={active || busy} onChange={(e) => setMinutes(Number(e.target.value))}>
              {[...new Set([5, 10, 15, 20, 30, shownMinutes])].sort((a, b) => a - b).map((m) => (
                <option key={m} value={m}>{m} min</option>
              ))}
            </select>
          </label>
          <button className="start" disabled={active || busy} onClick={() => onStart(fault, minutes)}>▶ Start demo</button>
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
            <span className="muted run-params">{FAULTS.find(([value]) => value === demo.fault)?.[1] ?? demo.fault} · {demo.minutes} min</span>
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
