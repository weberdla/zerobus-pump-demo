import { useEffect, useState } from "react";
import { describeDemo } from "./demoStatus.js";
import AlarmPanel from "./components/AlarmPanel.jsx";
import DemoControls from "./components/DemoControls.jsx";
import Gauge from "./components/Gauge.jsx";
import PumpGraphic from "./components/PumpGraphic.jsx";
import TagTable from "./components/TagTable.jsx";
import Trend from "./components/Trend.jsx";

const POLL_MS = 3000;
const TABS = [
  ["pump", "Pump"],
  ["trends", "Trends & tags"],
  ["demo", "Demo control"],
];
const tabFromHash = () => TABS.find(([id]) => `#${id}` === window.location.hash)?.[0] ?? "pump";

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function App() {
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [request, setRequest] = useState(null); // start or stop clicked, not yet reflected in the job status
  const [tab, setTab] = useState(tabFromHash);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch("/api/state");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const next = await response.json();
        if (alive) {
          setState(next);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    load();
    const poll = setInterval(load, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive = false;
      clearInterval(poll);
      clearInterval(tick);
    };
  }, []);

  const demo = state?.demo;
  // A start request is done once the run shows up; a stop request once the job is idle again.
  useEffect(() => {
    if (!request || busy) return;
    if ((request.kind === "start" && demo?.active) || (request.kind === "stop" && !demo?.active) || now - request.at > 120_000) {
      setRequest(null);
    }
  }, [request, busy, demo, now]);

  const showTab = (id) => {
    setTab(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  const control = async (kind, path, body) => {
    setBusy(true);
    setNotice(null);
    setRequest({ kind, at: Date.now() });
    try {
      const result = await postJson(path, body);
      if (!result.ok) {
        setNotice(result.message);
        setRequest(null);
      }
    } catch (e) {
      setNotice(`Request failed: ${e.message}`);
      setRequest(null);
    } finally {
      setBusy(false);
    }
  };

  if (!state) {
    return <div className="loading">{error ? `Cannot reach the HMI backend: ${error}` : "Connecting to PUMP-101…"}</div>;
  }

  const { tags, limits, health, alarms, trend } = state;
  const status = describeDemo(demo, { trend, tags, now, request, busy });
  // Between demo runs, silver still holds the last run's values: label them rather than judge them.
  const idle = !demo?.active && request?.kind !== "start" && Object.keys(tags).length > 0;

  // From Start until this run's readings arrive, the tables still hold the last run's values. Show only
  // readings from this run, so the screen starts blank instead of re-raising the last run's alarms.
  const runStart = request?.kind === "start" ? request.at
    : demo?.active && !demo.stop_only && demo.started_at ? Date.parse(demo.started_at) : null;
  const shown = runStart
    ? {
        tags: Object.fromEntries(Object.entries(tags).filter(([, t]) => t.event_ts && Date.parse(t.event_ts) >= runStart)),
        trend: trend.filter((p) => Date.parse(p.ts) + 10_000 > runStart), // 10-second buckets
      }
    : { tags, trend };
  shown.alarms = runStart ? alarms.filter((a) => a.tag in shown.tags) : alarms; // worst first, from the backend
  const waiting = runStart != null && Object.keys(shown.tags).length === 0;
  const shownHealth = !runStart ? health
    : shown.alarms[0]?.severity ?? ((shown.tags.Running?.value ?? 0) >= 0.5 ? "OK" : "STOPPED");
  const value = (name) => shown.tags[name]?.value ?? null;

  return (
    <div className="hmi">
      <header className="topbar">
        <div className="title">
          <div className="site">PLANT-A · PUMP STATION 1 · {state.mode === "mock" ? "MOCK DATA" : "LIVE"}</div>
          <h1>
            {state.equipment_id} <small>Centrifugal pump</small>
          </h1>
        </div>
        {idle ? (
          <div className="health idle">
            IDLE<small>last values</small>
          </div>
        ) : waiting ? (
          <div className="health waiting">
            STARTING<small>waiting for data</small>
          </div>
        ) : (
          <div className={`health ${shownHealth.replace(" ", "-").toLowerCase()}`}>{shownHealth}</div>
        )}
        <div className="meta">
          <div className="clock">{new Date(now).toLocaleTimeString([], { hour12: false })}</div>
          <div className="lag">
            {idle && state.newest_reading_at ? (
              <>Last reading <b>{new Date(state.newest_reading_at).toLocaleTimeString([], { hour12: false })}</b></>
            ) : (
              <>Silver lag <b>{waiting || state.silver_lag_s == null ? "--" : `${state.silver_lag_s.toFixed(1)} s`}</b></>
            )}
          </div>
        </div>
      </header>

      <nav className="navrow">
        <div className="tabs" role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={`tab ${tab === id ? "active" : ""}`} onClick={() => showTab(id)}>
              {label}
              {id === "demo" && status.short && <span className={`tab-chip ${status.tone}`}>{status.short}</span>}
            </button>
          ))}
        </div>
        <div className="datapath">
          <span>Simulator</span>→<span>Zerobus Ingest</span>→<span>Bronze · CDF</span>→<span>AUTO CDC</span>→
          <span className="here">Silver current state</span>
        </div>
      </nav>

      <AlarmPanel
        alarms={shown.alarms}
        idle={idle}
        waiting={waiting}
        error={error && `Connection lost (${error}). Showing the last values received.`}
        message={state.message}
      />

      <main className={`tab-body tab-${tab}`} role="tabpanel">
        {tab === "pump" && (
          <>
            <section className="panel graphic">
              <PumpGraphic tags={shown.tags} limits={limits} />
            </section>
            <section className="panel gauges">
              <Gauge label="Vibration" tag="VI-101" unit="mm/s" value={value("Vibration")} limits={limits.Vibration} decimals={2} />
              <Gauge label="Bearing temp" tag="TI-101" unit="°C" value={value("BearingTemp")} limits={limits.BearingTemp} />
              <Gauge label="Suction" tag="PI-101" unit="bar" value={value("SuctionPressure")} limits={limits.SuctionPressure} decimals={2} />
              <Gauge label="Flow" tag="FI-101" unit="m³/h" value={value("FlowRate")} limits={limits.FlowRate} />
            </section>
          </>
        )}
        {tab === "demo" && (
          <DemoControls
            demo={demo}
            status={status}
            busy={busy}
            notice={notice}
            onStart={(fault, minutes, warning, alarm) =>
              control("start", "/api/demo/start", { fault, minutes, warning_minutes: warning, alarm_minutes: alarm })}
            onStop={() => control("stop", "/api/demo/stop", {})}
          />
        )}
        {tab === "trends" && (
          <>
            <section className="panel trends">
              <Trend points={shown.trend} field="vibration" label="Bearing vibration · VI-101" unit="mm/s" limits={limits.Vibration}
                     color="#38bdf8" now={now} decimals={2} />
              <Trend points={shown.trend} field="bearing_temp" label="Bearing temperature · TI-101" unit="°C" limits={limits.BearingTemp}
                     color="#c084fc" now={now} />
            </section>
            <TagTable tags={shown.tags} now={now} />
          </>
        )}
      </main>

      <footer>
        Live values: silver <code>pump_tags_current</code> (AUTO CDC) · Trends: bronze <code>pump_tags_bronze</code> (Zerobus Ingest) ·
        refresh every {POLL_MS / 1000} s
      </footer>
    </div>
  );
}
