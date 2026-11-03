"""Data sources for the pump HMI: live (Databricks SQL + Jobs API) and mock (local simulator)."""

import datetime as dt
import itertools
import os
import pathlib
import sys
import threading
import time

# Alarm limits shared with the UI. Vibration and bearing-temperature limits match the
# dashboard; suction-pressure limits flag cavitation.
LIMITS = {
    "Vibration": {"warning": 4.5, "alarm": 7.1, "min": 0, "max": 10},
    "BearingTemp": {"warning": 65.0, "alarm": 75.0, "min": 20, "max": 100},
    "SuctionPressure": {"low_warning": 0.8, "low_alarm": 0.5, "min": 0, "max": 2},
    "DischargePressure": {"min": 0, "max": 10},
    "FlowRate": {"min": 0, "max": 150},
    "MotorCurrent": {"min": 0, "max": 60},
    "MotorSpeed": {"min": 0, "max": 2000},
}
SEVERITY_ORDER = {"ALARM": 2, "WARNING": 1}
DATA_TTL_S = 3.0  # minimum seconds between warehouse refreshes
STATUS_TTL_S = 2.0
IDLE_REFRESH_S = 90  # keep refreshing this long after a demo run ends, then let the warehouse sleep


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class AlarmTracker:
    """Evaluates alarm conditions and remembers when each alarm first became active."""

    def __init__(self):
        self.since = {}

    def evaluate(self, tags):
        def value(tag):
            return (tags.get(tag) or {}).get("value")

        active = []

        def high(tag, label):
            v, lim = value(tag), LIMITS[tag]
            if v is None:
                return
            if v > lim["alarm"]:
                active.append((f"{tag}-HH", tag, "ALARM", f"{label} high-high ({v:.1f} > {lim['alarm']})"))
            elif v > lim["warning"]:
                active.append((f"{tag}-H", tag, "WARNING", f"{label} high ({v:.1f} > {lim['warning']})"))

        high("Vibration", "Bearing vibration")
        high("BearingTemp", "Bearing temperature")
        running = (value("Running") or 0) >= 0.5
        suction, lim = value("SuctionPressure"), LIMITS["SuctionPressure"]
        if running and suction is not None:
            if suction < lim["low_alarm"]:
                active.append(("Suction-LL", "SuctionPressure", "ALARM", f"Suction pressure low-low ({suction:.2f} bar): cavitation"))
            elif suction < lim["low_warning"]:
                active.append(("Suction-L", "SuctionPressure", "WARNING", f"Suction pressure low ({suction:.2f} bar): cavitation risk"))
        for tag, info in tags.items():
            if info.get("quality") not in (None, "GOOD"):
                active.append((f"{tag}-Q", tag, "WARNING", f"{tag} sensor quality {info['quality']}"))

        now = utcnow().isoformat()
        keys = {key for key, *_ in active}
        self.since = {key: self.since.get(key, now) for key in keys}
        alarms = [{"key": k, "tag": t, "severity": s, "message": m, "since": self.since[k]} for k, t, s, m in active]
        alarms.sort(key=lambda a: (-SEVERITY_ORDER[a["severity"]], a["since"]))

        if not tags:
            health = "NO DATA"
        elif alarms:
            health = alarms[0]["severity"]
        else:
            health = "OK" if running else "STOPPED"
        return alarms, health


class LiveSource:
    """Reads silver/bronze through a SQL warehouse and controls the demo job via the Jobs API."""

    mode = "live"

    def __init__(self):
        from databricks.sdk import WorkspaceClient

        self.w = WorkspaceClient()  # app service principal in Databricks Apps; CLI profile locally
        self.catalog = os.environ["PUMP_CATALOG"]
        self.schema = os.environ["PUMP_SCHEMA"]
        self.warehouse_id = os.environ["WAREHOUSE_ID"]
        self.job_id = int(os.environ["DEMO_JOB_ID"])
        self.equipment_id = os.environ.get("EQUIPMENT_ID", "PUMP-101")
        self.alarms = AlarmTracker()
        self.lock = threading.Lock()
        self.data, self.data_at, self.data_error = None, 0.0, None
        self.status, self.status_at, self.last_active_at = None, 0.0, 0.0

    # ---- SQL ----
    def query(self, sql):
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        resp = self.w.statement_execution.execute_statement(
            statement=sql, warehouse_id=self.warehouse_id, catalog=self.catalog, schema=self.schema,
            parameters=[StatementParameterListItem(name="equipment_id", value=self.equipment_id)],
            wait_timeout="30s",
        )
        while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(0.5)
            resp = self.w.statement_execution.get_statement(resp.statement_id)
        if resp.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(resp.status.error.message if resp.status.error else resp.status.state.value)
        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, row)) for row in (resp.result.data_array or [])]

    def fetch_data(self):
        current = self.query(
            "SELECT tag_name, value, unit, quality, event_ts FROM pump_tags_current "
            "WHERE equipment_id = :equipment_id"
        )
        trend = self.query(
            "SELECT timestamp_seconds(floor(unix_timestamp(event_ts) / 10) * 10) AS ts, "
            "avg(value) FILTER (WHERE tag_name = 'Vibration') AS vibration, "
            "avg(value) FILTER (WHERE tag_name = 'BearingTemp') AS bearing_temp "
            "FROM pump_tags_bronze "
            "WHERE equipment_id = :equipment_id AND event_ts >= timestampadd(MINUTE, -10, current_timestamp()) "
            "GROUP BY 1 ORDER BY 1"
        )
        tags = {
            r["tag_name"]: {"value": None if r["value"] is None else float(r["value"]), "unit": r["unit"],
                            "quality": r["quality"], "event_ts": r["event_ts"]}
            for r in current
        }
        points = [{"ts": r["ts"], "vibration": _num(r["vibration"]), "bearing_temp": _num(r["bearing_temp"])} for r in trend]
        return tags, points

    # ---- Jobs ----
    def demo_status(self, force=False):
        if not force and self.status and time.time() - self.status_at < STATUS_TTL_S:
            return self.status
        runs = list(self.w.jobs.list_runs(job_id=self.job_id, active_only=True, expand_tasks=True, limit=1))
        if runs:
            status = _describe_active_run(runs[0])
            self.last_active_at = time.time()
        else:
            recent = self.w.jobs.list_runs(job_id=self.job_id, completed_only=True, expand_tasks=True, limit=5)
            last = next((r for r in itertools.islice(recent, 5) if not _stop_only(r)), None)
            status = {"active": False, "phase": "Idle", "last_run": _describe_finished_run(last)}
        self.status, self.status_at = status, time.time()
        return status

    def start_demo(self, fault, minutes):
        if self.demo_status(force=True)["active"]:
            return {"ok": False, "message": "A demo run is already in progress."}
        run = self.w.jobs.run_now(job_id=self.job_id, job_parameters={"fault": fault, "demo_minutes": str(minutes)})
        self.status_at = 0.0
        return {"ok": True, "run_id": run.response.run_id}

    def stop_demo(self):
        self.w.jobs.cancel_all_runs(job_id=self.job_id)
        deadline = time.time() + 90
        while time.time() < deadline and list(self.w.jobs.list_runs(job_id=self.job_id, active_only=True, limit=1)):
            time.sleep(2)
        # The stop task pauses the live silver job and stops the pipeline (it runs as the job owner).
        run = self.w.jobs.run_now(job_id=self.job_id, only=["stop_live_silver"])
        self.status_at = 0.0
        return {"ok": True, "run_id": run.response.run_id}

    # ---- Combined state ----
    def state(self):
        with self.lock:
            demo = self.demo_status()
            recently_active = demo["active"] or time.time() - self.last_active_at < IDLE_REFRESH_S
            if (self.data is None or recently_active) and time.time() - self.data_at > DATA_TTL_S:
                try:
                    self.data, self.data_error = self.fetch_data(), None
                except Exception as e:  # tables don't exist until the first demo run
                    self.data_error = str(e).splitlines()[0][:300]
                    self.data = self.data or ({}, [])
                self.data_at = time.time()
            tags, trend = self.data
            return build_state(self, tags, trend, demo, self.data_at, self.data_error)


class MockSource:
    """Local stand-in that runs the demo's PumpSimulator in-process (HMI_MOCK=1).

    HMI_MOCK_SPEED=30 runs the simulation 30x faster, so a fault develops in about 30 seconds.
    A started demo steps through the job's phases on a short timeline (MOCK_TIMELINE_S). Between
    runs the screen keeps the last values, as it does live; at startup they come from a healthy run.
    """

    mode = "mock"
    # Seconds after the start: bronze created, first readings streamed, silver live; then the stop step.
    MOCK_TIMELINE_S = {"bronze": 6, "streaming": 14, "silver": 22, "stop": 6}

    def __init__(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from pump_simulator import PumpSimulator, TAGS

        self.PumpSimulator, self.TAGS = PumpSimulator, TAGS
        self.equipment_id = "PUMP-101"
        self.alarms = AlarmTracker()
        self.lock = threading.Lock()
        self.pump = PumpSimulator(stops=False)
        self.step_s = 1.0 / float(os.environ.get("HMI_MOCK_SPEED", "1"))
        self.last_step = time.time()
        self.history = [(self.last_step, self.pump.step(1.0)) for _ in range(600)]
        self.silver = (self.history[-1][1], utcnow() - dt.timedelta(seconds=9))  # (values, as_of) last pushed to "silver"
        self.streaming = False
        self.run = None  # {"fault", "minutes", "started", "stopped"}
        self.last_run = None

    def _elapsed(self):
        return time.time() - self.run["started"] if self.run else None

    def _advance(self):
        now, t = time.time(), self.MOCK_TIMELINE_S
        elapsed = self._elapsed()
        streaming = (elapsed is not None and not self.run.get("stopped")
                     and t["streaming"] <= elapsed < t["streaming"] + self.run["minutes"] * 60)
        if streaming and not self.streaming:
            # This run's readings replace the last run's, from the moment streaming began.
            self.last_step, self.history = self.run["started"] + t["streaming"], []
        self.streaming = streaming
        if streaming:
            while now - self.last_step >= self.step_s:
                self.last_step += self.step_s
                self.history.append((self.last_step, self.pump.step(1.0)))
            self.history = self.history[-600:]  # last 10 simulated minutes
            if self.history and elapsed >= t["silver"]:
                self.silver = (self.history[-1][1], utcnow() - dt.timedelta(seconds=9))
        if self.run:
            end = self.run.get("stopped") or self.run["started"] + t["streaming"] + self.run["minutes"] * 60
            if now > end + t["stop"]:
                result = "CANCELED" if self.run.get("stopped") else "SUCCESS"
                self.last_run = {"run_id": 0, "result": result, "ended_at": utcnow().isoformat(), "run_url": None,
                                 "fault": self.run["fault"], "minutes": self.run["minutes"]}
                self.run = None

    def start_demo(self, fault, minutes):
        with self.lock:
            if self.run:
                return {"ok": False, "message": "A demo run is already in progress."}
            self.pump = self.PumpSimulator(fault=fault, stops=False)
            self.run = {"fault": fault, "minutes": minutes, "started": time.time()}
        return {"ok": True, "run_id": 0}

    def stop_demo(self):
        with self.lock:
            if self.run and not self.run.get("stopped"):
                self.run["stopped"] = time.time()
        return {"ok": True, "run_id": 0}

    def _demo(self):
        if not self.run:
            return {"active": False, "phase": "Idle", "last_run": self.last_run}
        t, elapsed, now = self.MOCK_TIMELINE_S, self._elapsed(), time.time()
        iso = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()
        started = self.run["started"]
        if self.run.get("stopped"):
            return {"active": True, "phase": "Stopping live silver", "stop_only": True, "run_url": None,
                    "started_at": iso(self.run["stopped"]), "steps": [{"key": "stop_live_silver", "state": "running"}]}
        stream_end = started + t["streaming"] + self.run["minutes"] * 60
        stage = lambda begin, finish: "pending" if now < begin else ("running" if now < finish else "done")
        steps = {
            "create_bronze": stage(started, started + t["bronze"]),
            "start_live_silver": stage(started + t["bronze"], started + t["silver"]),
            "stream_pump_data": stage(started + t["bronze"], stream_end),
            "stop_live_silver": stage(stream_end, stream_end + t["stop"]),
        }
        return {"active": True, "phase": "Mock run", "fault": self.run["fault"], "minutes": self.run["minutes"],
                "run_url": None, "started_at": iso(started), "stop_only": False,
                "streaming_started_at": iso(started + t["streaming"]) if elapsed >= t["streaming"] else None,
                "steps": [{"key": key, "state": steps[key]} for key in STEPS]}

    def state(self):
        with self.lock:
            self._advance()
            tags = {}
            if self.silver:
                values, as_of = self.silver
                tags = {name: {"value": round(values[name], 3), "unit": unit, "quality": "GOOD", "event_ts": as_of.isoformat()}
                        for name, unit in self.TAGS.items()}
            # Stamp readings in simulated time (one per second, newest = the last step) so trends span 10 minutes.
            buckets, end = {}, self.last_step
            for i, (_, v) in enumerate(self.history):
                t = end - (len(self.history) - 1 - i)
                buckets.setdefault(int(t // 10) * 10, []).append(v)
            trend = [{"ts": dt.datetime.fromtimestamp(b, dt.timezone.utc).isoformat(),
                      "vibration": sum(v["Vibration"] for v in vs) / len(vs),
                      "bearing_temp": sum(v["BearingTemp"] for v in vs) / len(vs)} for b, vs in sorted(buckets.items())]
            return build_state(self, tags, trend, self._demo(), time.time(), None)


def build_state(source, tags, trend, demo, data_at, error):
    alarms, health = source.alarms.evaluate(tags)
    newest = max((parse_ts(t["event_ts"]) for t in tags.values() if t.get("event_ts")), default=None)
    return {
        "mode": source.mode,
        "equipment_id": source.equipment_id,
        "tags": tags,
        "trend": trend,
        "alarms": alarms,
        "health": health,
        "limits": LIMITS,
        "silver_lag_s": round((utcnow() - newest).total_seconds(), 1) if newest else None,
        "newest_reading_at": newest.isoformat() if newest else None,
        "data_as_of": dt.datetime.fromtimestamp(data_at, dt.timezone.utc).isoformat() if data_at else None,
        "message": "Waiting for the first demo run to create the tables." if error and not tags else None,
        "demo": demo,
    }


def _num(value):
    return None if value is None else float(value)


def _ms_to_iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat() if ms else None


# The demo job's tasks, in the order they run.
STEPS = ["create_bronze", "start_live_silver", "stream_pump_data", "stop_live_silver"]


def _stop_only(run):
    """True for the run the Stop button starts: only the stop_live_silver task."""
    return not any(t.task_key == "create_bronze" for t in run.tasks or [])


def _task_state(task):
    life = task.state.life_cycle_state.value if task.state and task.state.life_cycle_state else "PENDING"
    result = task.state.result_state.value if task.state and task.state.result_state else None
    if life in ("PENDING", "QUEUED", "BLOCKED", "WAITING_FOR_RETRY"):
        return "pending"
    if life in ("RUNNING", "TERMINATING"):
        return "running"
    if life == "SKIPPED" or result in ("EXCLUDED", "UPSTREAM_CANCELED", "UPSTREAM_FAILED"):
        return "skipped"
    return {"SUCCESS": "done", "SUCCESS_WITH_FAILURES": "done", "CANCELED": "cancelled"}.get(result, "failed")


def _describe_active_run(run):
    states = {t.task_key: (t.state.life_cycle_state.value if t.state and t.state.life_cycle_state else "PENDING")
              for t in run.tasks or []}
    tasks = {t.task_key: t for t in run.tasks or []}
    params = {p.name: p.value or p.default for p in run.job_parameters or []}
    stream = next((t for t in run.tasks or [] if t.task_key == "stream_pump_data"), None)
    if "create_bronze" not in states or states.get("stream_pump_data") in ("TERMINATED", "SKIPPED"):
        phase = "Stopping live silver"
    elif states.get("create_bronze") != "TERMINATED":
        phase = "Creating bronze table"
    elif states.get("stream_pump_data") == "RUNNING":
        phase = "Streaming · silver live" if states.get("start_live_silver") == "TERMINATED" else "Streaming · starting silver"
    else:
        phase = "Starting"
    return {
        "active": True,
        "phase": phase,
        "run_id": run.run_id,
        "run_url": run.run_page_url,
        "fault": params.get("fault"),
        "minutes": int(params["demo_minutes"]) if params.get("demo_minutes") else None,
        "started_at": _ms_to_iso(run.start_time),
        "streaming_started_at": _ms_to_iso(stream.start_time) if stream and states.get("stream_pump_data") == "RUNNING" else None,
        "stop_only": _stop_only(run),
        "steps": [{"key": key, "state": _task_state(tasks[key])} for key in STEPS if key in tasks],
    }


def _describe_finished_run(run):
    if run is None:
        return None
    result = run.state.result_state.value if run.state and run.state.result_state else None
    params = {p.name: p.value or p.default for p in run.job_parameters or []}
    return {"run_id": run.run_id, "result": result, "ended_at": _ms_to_iso(run.end_time), "run_url": run.run_page_url,
            "fault": params.get("fault"), "minutes": int(params["demo_minutes"]) if params.get("demo_minutes") else None}
