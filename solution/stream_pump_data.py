# Databricks notebook source
# MAGIC %md
# MAGIC # Stream simulated pump data through Zerobus Ingest
# MAGIC
# MAGIC Runs the pump simulator (`pump_simulator.py`, next to this notebook) and streams its
# MAGIC readings into the bronze table. The simulator's scheduled stops (30-60 seconds every
# MAGIC 5-10 minutes) are turned off, so a fault develops without interruption.
# MAGIC
# MAGIC `warning_minutes` and `alarm_minutes` set when the fault first raises a WARNING and an ALARM
# MAGIC (the alarm time applies to a bearing fault). Leave them empty for the defaults: 7 and 13
# MAGIC minutes for a bearing fault, 7.5 minutes for cavitation.
# MAGIC
# MAGIC With `simulator` set to `off`, another source (for example, Ignition) sends the readings. The
# MAGIC notebook then streams nothing; it keeps the run, and so the live silver pipeline, going for the
# MAGIC demo's duration, and reports how many readings reach bronze each minute. For the Ignition
# MAGIC Zerobus Connector module it also reports the tag events landing in `ignition_table`, which the
# MAGIC silver pipeline maps into bronze.

# COMMAND ----------

# MAGIC %pip install databricks-zerobus-ingest-sdk==1.10.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("server_endpoint", "")
dbutils.widgets.text("table_name", "")
dbutils.widgets.text("ignition_table", "")
dbutils.widgets.text("secret_scope", "")
dbutils.widgets.text("duration_minutes", "15")
dbutils.widgets.text("fault", "bearing")
dbutils.widgets.text("warning_minutes", "")
dbutils.widgets.text("alarm_minutes", "")
dbutils.widgets.text("simulator", "on")

# COMMAND ----------

import time

duration_s = float(dbutils.widgets.get("duration_minutes")) * 60
if dbutils.widgets.get("simulator").strip().lower() == "off":
    bronze = dbutils.widgets.get("table_name")
    ignition = dbutils.widgets.get("ignition_table").strip()
    end = time.monotonic() + duration_s
    print(f"Simulator off: keeping the live pipeline going for {duration_s / 60:g} minutes for another data feed.")
    while time.monotonic() < end:
        time.sleep(min(60.0, end - time.monotonic()))
        # Read the table again each time, so the count includes the newest commits.
        readings = spark.table(bronze).where("event_ts >= current_timestamp() - INTERVAL 1 MINUTE").count()
        message = f"{readings} readings reached bronze in the last minute"
        if ignition and spark.catalog.tableExists(ignition):
            events = spark.table(ignition).where("event_time >= current_timestamp() - INTERVAL 1 MINUTE").count()
            message += f" ({events} Ignition tag events landed in {ignition.rsplit('.', 1)[-1]})"
        print(message)
    dbutils.notebook.exit("simulator off")

# COMMAND ----------

import logging

from databricks.sdk import WorkspaceClient

from pump_simulator import ZerobusConfig, run_simulation  # solution/pump_simulator.py, next to this notebook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)

scope = dbutils.widgets.get("secret_scope")
cfg = ZerobusConfig(
    server_endpoint=dbutils.widgets.get("server_endpoint"),
    workspace_url=WorkspaceClient().config.host,
    table_name=dbutils.widgets.get("table_name"),
    client_id=dbutils.secrets.get(scope, "client-id"),
    client_secret=dbutils.secrets.get(scope, "client-secret"),
)

# COMMAND ----------

def minutes(name):
    value = dbutils.widgets.get(name).strip()
    return float(value) if value else None


# One scan per second; the stream is flushed and closed when the run ends or is cancelled.
run_simulation(
    cfg,
    duration=duration_s,
    fault=dbutils.widgets.get("fault"),
    stops=False,
    warning_minutes=minutes("warning_minutes"),
    alarm_minutes=minutes("alarm_minutes"),
)
