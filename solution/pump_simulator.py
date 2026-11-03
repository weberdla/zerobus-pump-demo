#!/usr/bin/env python3
"""Centrifugal pump tag simulator for the Zerobus Ingest demo.

Generates one reading per tag every scan for a single pump and streams the
readings, as JSON, into a Unity Catalog Delta table through Zerobus Ingest.

Run locally (connection settings come from ZEROBUS_* environment variables):
    python pump_simulator.py                  # normal operation, Ctrl+C to stop
    python pump_simulator.py --fault bearing  # bearing slowly degrades
    python pump_simulator.py --dry-run        # print records, send nothing
    python pump_simulator.py --send-stale     # send one out-of-order scan, then exit

Or import ZerobusConfig and run_simulation() from a Databricks notebook.
"""

import argparse
import json
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass

from zerobus.sdk.shared import NonRetriableException, TableProperties
from zerobus.sdk.sync import ZerobusSdk

log = logging.getLogger("pump_simulator")

# tag_name -> engineering unit. Each scan writes one bronze row per tag.
TAGS = {
    "Running": "bool",
    "MotorSpeed": "rpm",
    "MotorCurrent": "A",
    "FlowRate": "m3/h",
    "SuctionPressure": "bar",
    "DischargePressure": "bar",
    "BearingTemp": "degC",
    "Vibration": "mm/s",
}

RATED_RPM = 1780.0
RATED_FLOW = 120.0  # m3/h at the best efficiency point
AMBIENT_C = 25.0


@dataclass
class ZerobusConfig:
    server_endpoint: str
    workspace_url: str
    table_name: str
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls):
        env_vars = {
            "server_endpoint": "ZEROBUS_SERVER_ENDPOINT",
            "workspace_url": "ZEROBUS_WORKSPACE_URL",
            "table_name": "ZEROBUS_TABLE_NAME",
            "client_id": "ZEROBUS_CLIENT_ID",
            "client_secret": "ZEROBUS_CLIENT_SECRET",
        }
        missing = [name for name in env_vars.values() if not os.getenv(name)]
        if missing:
            sys.exit("Missing environment variables: " + ", ".join(missing))
        return cls(**{field: os.environ[name] for field, name in env_vars.items()})

    def open_stream(self):
        sdk = ZerobusSdk(self.server_endpoint, self.workspace_url, application_name="zerobus-pump-demo/1.0")
        # No Protobuf descriptor or Avro schema in TableProperties = JSON records.
        return sdk.create_stream(self.client_id, self.client_secret, TableProperties(self.table_name))


def now_us():
    """Current time in microseconds since the Unix epoch (Zerobus JSON TIMESTAMP format)."""
    return time.time_ns() // 1000


class PumpSimulator:
    """Small physical model of a centrifugal pump with optional faults."""

    def __init__(self, equipment_id="PUMP-101", site="PLANT-A", fault="none", stops=True):
        self.equipment_id = equipment_id
        self.site = site
        self.fault = fault
        self.stops = stops
        self.running = True
        self.speed = RATED_RPM
        self.bearing_temp = AMBIENT_C + 30.0
        self.fault_level = 0.0  # 0 = healthy, 1 = fully developed fault
        self.elapsed = 0.0
        self.state_until = random.uniform(300, 600)

    def _update_run_state(self):
        # Run for 5-10 minutes, stop for 30-60 seconds, repeat.
        if not self.stops or self.elapsed < self.state_until:
            return
        self.running = not self.running
        self.state_until = self.elapsed + (random.uniform(300, 600) if self.running else random.uniform(30, 60))
        log.info("%s %s", self.equipment_id, "STARTED" if self.running else "STOPPED")

    def step(self, dt):
        """Advance the model by dt seconds and return {tag_name: value}."""
        self.elapsed += dt
        self._update_run_state()

        # Motor ramps toward rated speed (running) or zero (stopped) over ~5 s.
        target_rpm = RATED_RPM if self.running else 0.0
        self.speed += (target_rpm - self.speed) * min(1.0, dt / 5.0)
        n = self.speed / RATED_RPM  # speed fraction, 0..1

        if self.fault != "none":
            self.fault_level = min(1.0, self.fault_level + dt / 900.0)  # fully developed after ~15 min
        bearing = self.fault_level if self.fault == "bearing" else 0.0
        cavitation = self.fault_level if self.fault == "cavitation" else 0.0

        # Process demand swings +/-10% over a 10-minute cycle.
        demand = 0.85 + 0.10 * math.sin(2 * math.pi * self.elapsed / 600.0)
        flow = max(0.0, RATED_FLOW * demand * n * (1 - 0.3 * cavitation) + random.gauss(0, 1.0) * n)
        q = flow / RATED_FLOW
        suction = 1.2 - 0.8 * cavitation + random.gauss(0, 0.02)
        discharge = suction + 5.0 * n**2 * (1.2 - 0.25 * q**2) + random.gauss(0, 0.03)
        current = (8.0 + 34.0 * q + random.gauss(0, 0.3)) * n

        # Bearing temperature lags behind load with a ~2 minute time constant.
        target_temp = AMBIENT_C + 30.0 * n + 25.0 * bearing
        self.bearing_temp += (target_temp - self.bearing_temp) * min(1.0, dt / 120.0)

        vibration = (1.8 + 6.0 * bearing) * n + 4.0 * cavitation * n * random.random() + abs(random.gauss(0, 0.1))

        return {
            "Running": 1.0 if self.running else 0.0,
            "MotorSpeed": self.speed + random.gauss(0, 2.0) * n,
            "MotorCurrent": max(0.0, current),
            "FlowRate": flow,
            "SuctionPressure": suction,
            "DischargePressure": discharge,
            "BearingTemp": self.bearing_temp + random.gauss(0, 0.05),
            "Vibration": vibration,
        }

    def scan(self, dt):
        """Return one JSON-ready record per tag, all sharing the same scan timestamp."""
        event_ts = now_us()
        records = []
        for tag_name, value in self.step(dt).items():
            quality = "GOOD"
            if random.random() < 0.005:  # ~0.5% sensor dropouts
                value, quality = None, "BAD"
            records.append({
                "equipment_id": self.equipment_id,
                "site": self.site,
                "tag_name": tag_name,
                "value": None if value is None else round(value, 3),
                "unit": TAGS[tag_name],
                "quality": quality,
                "event_ts": event_ts,
            })
        return records


def run_simulation(cfg, equipment_id="PUMP-101", site="PLANT-A", interval=1.0, duration=None,
                   fault="none", stops=True, dry_run=False):
    """Stream pump scans to Zerobus until `duration` seconds pass or the run is interrupted."""
    pump = PumpSimulator(equipment_id, site, fault, stops)
    stream = None if dry_run else cfg.open_stream()
    if stream:
        log.info("Stream open to %s", cfg.table_name)

    scans = sent = 0
    started = time.monotonic()
    try:
        while duration is None or time.monotonic() - started < duration:
            records = pump.scan(interval)
            if dry_run:
                for record in records:
                    print(json.dumps(record))
            else:
                stream.ingest_records_offset(records)  # queues the scan; acks arrive in the background
            scans += 1
            sent += len(records)
            if stream and scans % 10 == 0:
                stream.flush()  # blocks until everything sent so far is durable in the table
                log.info("%d records durably committed", sent)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Stopping...")
    finally:
        if stream:
            stream.close()  # flushes anything still in flight
    log.info("Done: %d scans, %d records", scans, sent)


def send_stale_records(cfg, equipment_id="PUMP-101", site="PLANT-A", minutes_old=10):
    """Send one obviously wrong scan (value -1) timestamped in the past.

    The rows land in bronze, but AUTO CDC must not let them overwrite the newer
    values already in the silver current-state table.
    """
    event_ts = now_us() - minutes_old * 60 * 1_000_000
    records = [
        {"equipment_id": equipment_id, "site": site, "tag_name": tag_name, "value": -1.0,
         "unit": unit, "quality": "GOOD", "event_ts": event_ts}
        for tag_name, unit in TAGS.items()
    ]
    stream = cfg.open_stream()
    try:
        stream.ingest_records_offset(records)
        stream.flush()
    finally:
        stream.close()
    log.info("Sent %d stale records timestamped %d minutes ago", len(records), minutes_old)


def main():
    parser = argparse.ArgumentParser(description="Stream simulated pump tags to Databricks via Zerobus Ingest.")
    parser.add_argument("--equipment-id", default="PUMP-101")
    parser.add_argument("--site", default="PLANT-A")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between scans (default: 1)")
    parser.add_argument("--duration", type=float, help="stop after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--fault", choices=["none", "bearing", "cavitation"], default="none")
    parser.add_argument("--no-stops", action="store_true", help="keep the pump running the whole time")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print records instead of sending them")
    mode.add_argument("--send-stale", action="store_true", help="send one out-of-order scan, then exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = None if args.dry_run else ZerobusConfig.from_env()
    try:
        if args.send_stale:
            send_stale_records(cfg, args.equipment_id, args.site)
        else:
            run_simulation(cfg, args.equipment_id, args.site, args.interval, args.duration,
                           args.fault, not args.no_stops, args.dry_run)
    except NonRetriableException as e:
        log.error("Zerobus rejected the request: %s", e)
        log.error("Check the endpoint, table name, service principal credentials, and grants.")
        sys.exit(1)


if __name__ == "__main__":
    main()
