# Databricks notebook source
# MAGIC %md
# MAGIC # Start or stop the live silver pipeline
# MAGIC
# MAGIC `start` unpauses the `zerobus_pump_silver_live` continuous job and waits for the pipeline to run.
# MAGIC `stop` pauses that job, cancels its run, and waits for the pipeline to go idle.

# COMMAND ----------

import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs
from databricks.sdk.service.pipelines import PipelineState

dbutils.widgets.dropdown("action", "start", ["start", "stop"])
dbutils.widgets.text("live_job_id", "")
dbutils.widgets.text("pipeline_id", "")

action = dbutils.widgets.get("action")
live_job_id = int(dbutils.widgets.get("live_job_id"))
pipeline_id = dbutils.widgets.get("pipeline_id")
w = WorkspaceClient()


def set_live_job(pause_status):
    w.jobs.update(job_id=live_job_id, new_settings=jobs.JobSettings(continuous=jobs.Continuous(pause_status=pause_status)))


def wait_for_pipeline(state, timeout_s=900):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        current = w.pipelines.get(pipeline_id).state
        if current == state:
            return
        print(f"pipeline is {current.value if current else 'unknown'}, waiting for {state.value}...")
        time.sleep(15)
    raise TimeoutError(f"pipeline {pipeline_id} did not reach {state.value} within {timeout_s}s")

# COMMAND ----------

if action == "start":
    set_live_job(jobs.PauseStatus.UNPAUSED)
    wait_for_pipeline(PipelineState.RUNNING)
    print("Live silver pipeline is running.")
else:
    set_live_job(jobs.PauseStatus.PAUSED)
    w.jobs.cancel_all_runs(job_id=live_job_id)
    if w.pipelines.get(pipeline_id).state != PipelineState.IDLE:
        w.pipelines.stop(pipeline_id=pipeline_id)
    wait_for_pipeline(PipelineState.IDLE)
    print("Live silver pipeline is stopped.")
