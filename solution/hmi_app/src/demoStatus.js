// Describes where a demo run is, from the job's task states plus the data on screen:
// "streaming" means this run's readings reached bronze, "live" means they reached silver.

// Typical timings from validation runs, measured from the job start.
const FIRST_READINGS_S = 30;
const SILVER_LIVE_S = 75;
const BUCKET_MS = 10_000; // bronze trend points are 10-second buckets

export const mmss = (ms) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false });

const LAST_RESULT = {
  SUCCESS: ["idle", "finished"],
  CANCELED: ["idle", "was stopped"],
  FAILED: ["error", "failed"],
  TIMEDOUT: ["error", "timed out"],
};

// Returns { tone, headline, detail, short } plus the run's progress while it streams.
export function describeDemo(demo, { trend, tags, now, request, busy }) {
  if (request?.kind === "stop" && (busy || (demo?.active && !demo.stop_only))) {
    return { tone: "stopping", headline: "Stopping the demo", detail: "Cancelling the run…", short: "Stopping" };
  }
  if (!demo?.active) {
    if (request?.kind === "start") {
      return { tone: "starting", headline: "Starting the demo", detail: "Submitting the demo job…", short: "Starting" };
    }
    const last = demo?.last_run;
    if (!last) return { tone: "idle", headline: "Ready", detail: "Choose a fault and a duration, then start the demo." };
    const [tone, what] = LAST_RESULT[last.result] ?? ["error", `ended (${last.result ?? "unknown"})`];
    const at = last.ended_at ? ` at ${clock(last.ended_at)}` : "";
    return { tone, headline: "Ready", detail: `The last demo ${what}${at}.` };
  }
  if (demo.stop_only) {
    return {
      tone: "stopping",
      headline: "Stopping live silver",
      detail: "The run was cancelled. Shutting down the live silver pipeline; this takes about 30 seconds.",
      short: "Stopping",
    };
  }

  const steps = Object.fromEntries((demo.steps ?? []).map((s) => [s.key, s.state]));
  const external = demo.simulator === false; // another source, such as Ignition, sends the readings
  const started = demo.started_at ? Date.parse(demo.started_at) : now;
  const elapsed = (now - started) / 1000;
  const eta = (target) => (elapsed < target ? `in about ${Math.round(target - elapsed)} s` : "any moment now");

  if (steps.stream_pump_data && !["pending", "running"].includes(steps.stream_pump_data)) {
    return { tone: "stopping", headline: "Stream finished", detail: "Stopping the live silver pipeline…", short: "Stopping" };
  }
  if (steps.create_bronze !== "done") {
    return {
      tone: "starting",
      headline: "Creating the bronze table",
      detail: external
        ? "Creating the table and its grants. Then the screen waits for your external feed."
        : `Creating the table and its grants. Streaming begins ${eta(FIRST_READINGS_S)}.`,
      short: "Starting",
    };
  }
  const inBronze = trend.some((p) => Date.parse(p.ts) + BUCKET_MS > started);
  if (!inBronze && external) {
    return {
      tone: "starting",
      headline: "Waiting for the external feed",
      detail: "The simulator is off. Start your feed, such as Ignition, sending PUMP-101 readings to the Zerobus endpoint; they show here when they reach bronze.",
      short: "Waiting",
    };
  }
  if (!inBronze) {
    return {
      tone: "starting",
      headline: "Starting the simulator",
      detail: `Installing the Zerobus SDK and opening the stream. Streaming begins ${eta(FIRST_READINGS_S)}.`,
      short: "Starting",
    };
  }
  const progress = demo.streaming_started_at && demo.minutes
    ? (() => {
        const ran = now - Date.parse(demo.streaming_started_at);
        return { frac: Math.min(1, ran / (demo.minutes * 60000)), left: demo.minutes * 60000 - ran };
      })()
    : null;
  const inSilver = Object.values(tags).some((t) => t.event_ts && Date.parse(t.event_ts) >= started);
  if (!inSilver) {
    return {
      tone: "streaming",
      headline: "Streaming into bronze",
      detail: `${external ? "Readings from the external feed" : "Readings"} are landing in bronze through Zerobus Ingest. Silver goes live ${eta(SILVER_LIVE_S)}, once the pipeline is running.`,
      short: "Streaming",
      progress,
    };
  }
  return {
    tone: "live",
    headline: "Live",
    detail: `Readings flow from the ${external ? "external feed" : "simulator"} through Zerobus Ingest into bronze, and AUTO CDC keeps silver current.`,
    short: progress ? `Live · ${mmss(progress.left)}` : "Live",
    progress,
  };
}

// State of each job step for display; the simulator's stream step reads "starting" until this run's data
// arrives. With an external feed, the step is just keeping the pipeline live, so it stays "running".
export function stepStates(demo, status) {
  return (demo?.steps ?? []).map((step) => {
    if (step.key === "stream_pump_data" && step.state === "running" && status.tone === "starting" && demo.simulator !== false) {
      return { ...step, state: "starting" };
    }
    return step;
  });
}
