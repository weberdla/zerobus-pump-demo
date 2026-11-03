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

# COMMAND ----------

# MAGIC %pip install databricks-zerobus-ingest-sdk==1.10.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("server_endpoint", "")
dbutils.widgets.text("table_name", "")
dbutils.widgets.text("secret_scope", "")
dbutils.widgets.text("duration_minutes", "15")
dbutils.widgets.text("fault", "bearing")
dbutils.widgets.text("warning_minutes", "")
dbutils.widgets.text("alarm_minutes", "")

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
    duration=float(dbutils.widgets.get("duration_minutes")) * 60,
    fault=dbutils.widgets.get("fault"),
    stops=False,
    warning_minutes=minutes("warning_minutes"),
    alarm_minutes=minutes("alarm_minutes"),
)
