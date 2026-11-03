import { useState } from "react";

const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false });

// Annunciator strip: one fixed-height row, so the screen below never moves when alarms come and go.
// Alarms sit side by side, worst first; unacknowledged ones flash until an operator clicks ACK. Between
// demo runs (idle) the alarms come from the last run's values, so they're greyed out, without flashing
// or ACK. A lost connection and the backend's messages show in the same strip.
export default function AlarmPanel({ alarms, idle, waiting, error, message }) {
  const [acked, setAcked] = useState(() => new Set());
  const cells = [];

  if (error) {
    cells.push(
      <div key="error" className="alarm-row notice error">
        <span className="alarm-msg" title={error}>{error}</span>
      </div>,
    );
  }
  for (const a of alarms) {
    if (idle) {
      cells.push(
        <div key={a.key} className={`alarm-row idle ${a.severity.toLowerCase()}`}>
          <span className="alarm-sev">{a.severity}</span>
          <span className="alarm-msg" title={a.message}>{a.message}</span>
          <span className="alarm-since">last run</span>
        </div>,
      );
      continue;
    }
    const isAcked = acked.has(a.key + a.since);
    cells.push(
      <div key={a.key} className={`alarm-row ${a.severity.toLowerCase()} ${isAcked ? "acked" : "unacked"}`}>
        <span className="alarm-sev">{a.severity}</span>
        <span className="alarm-msg" title={a.message}>{a.message}</span>
        <span className="alarm-since">since {clock(a.since)}</span>
        {!isAcked && <button onClick={() => setAcked(new Set(acked).add(a.key + a.since))}>ACK</button>}
      </div>,
    );
  }
  if (!alarms.length) {
    const text = message ?? (waiting ? "Waiting for this run's readings" : "No active alarms");
    cells.push(
      <div key="quiet" className={`alarm-row quiet ${message ? "info" : ""}`}>
        <span className="alarm-msg" title={text}><b>●</b> {text}</span>
      </div>,
    );
  }
  return <div className="alarms" role="status">{cells}</div>;
}
