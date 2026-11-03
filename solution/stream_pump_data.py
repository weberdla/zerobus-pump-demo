# Databricks notebook source
# MAGIC %md
# MAGIC # Stream simulated pump data through Zerobus Ingest
# MAGIC
# MAGIC Runs the pump simulator (`pump_simulator.py`, next to this notebook) and streams its
# MAGIC readings into the bronze table. The simulator's scheduled stops (30-60 seconds every
# MAGIC 5-10 minutes) are turned off, so a fault develops without interruption.

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

# One scan per second; the stream is flushed and closed when the run ends or is cancelled.
run_simulation(
    cfg,
    duration=float(dbutils.widgets.get("duration_minutes")) * 60,
    fault=dbutils.widgets.get("fault"),
    stops=False,
)
