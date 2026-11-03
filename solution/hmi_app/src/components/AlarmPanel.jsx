import { useState } from "react";

const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false });

// Annunciator: unacknowledged alarms flash until an operator clicks ACK. Between demo runs (idle) the
// alarms come from the last run's values, so they're shown greyed out, without flashing or ACK.
export default function AlarmPanel({ alarms, idle, waiting }) {
  const [acked, setAcked] = useState(() => new Set());

  if (!alarms.length) {
    return <div className="alarms quiet">● {waiting ? "Waiting for this run's readings" : "No active alarms"}</div>;
  }
  return (
    <div className="alarms">
      {alarms.map((a) => {
        if (idle) {
          return (
            <div key={a.key} className={`alarm-row idle ${a.severity.toLowerCase()}`}>
              <span className="alarm-sev">{a.severity}</span>
              <span className="alarm-msg">{a.message}</span>
              <span className="alarm-since">last run</span>
            </div>
          );
        }
        const isAcked = acked.has(a.key + a.since);
        return (
          <div key={a.key} className={`alarm-row ${a.severity.toLowerCase()} ${isAcked ? "acked" : "unacked"}`}>
            <span className="alarm-sev">{a.severity}</span>
            <span className="alarm-msg">{a.message}</span>
            <span className="alarm-since">since {clock(a.since)}</span>
            {!isAcked && (
              <button onClick={() => setAcked(new Set(acked).add(a.key + a.since))}>ACK</button>
            )}
          </div>
        );
      })}
    </div>
  );
}
