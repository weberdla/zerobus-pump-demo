# Databricks notebook source
# MAGIC %md
# MAGIC # Create the bronze table and grant access
# MAGIC
# MAGIC Creates the bronze table with Change Data Feed on, gives the Zerobus service principal
# MAGIC write access to it, and gives the HMI app's service principal read access to the schema.
# MAGIC
# MAGIC Also creates `ignition_events_bronze`, the landing table for the Ignition Zerobus Connector
# MAGIC module. The module writes its own fixed record format, so the silver pipeline maps those rows
# MAGIC into `pump_tags_bronze` (see `pump_silver_pipeline.py`). The table stays empty when the
# MAGIC simulator feeds the demo. Safe to re-run.

# COMMAND ----------

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("sp_application_id", "")
dbutils.widgets.text("app_name", "")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
sp = dbutils.widgets.get("sp_application_id")
app_name = dbutils.widgets.get("app_name")
bronze = f"`{catalog}`.`{schema}`.pump_tags_bronze"
ignition = f"`{catalog}`.`{schema}`.ignition_events_bronze"

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {bronze} (
  equipment_id STRING    COMMENT 'Asset ID, e.g. PUMP-101',
  site         STRING    COMMENT 'Plant or site code',
  tag_name     STRING    COMMENT 'Tag (signal) name, e.g. DischargePressure',
  value        DOUBLE    COMMENT 'Reading in engineering units; NULL when quality is BAD',
  unit         STRING    COMMENT 'Engineering unit, e.g. bar, rpm, degC',
  quality      STRING    COMMENT 'OPC UA-style quality: GOOD, UNCERTAIN, BAD',
  event_ts     TIMESTAMP COMMENT 'Scan time at the source (UTC)'
)
COMMENT 'Bronze: raw pump tag readings streamed in by Zerobus Ingest'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")

# COMMAND ----------

# Landing table for the Ignition Zerobus Connector module (github.com/pravinva/lakeflow-ignition-zerobus-connector).
# Columns, types and order must match the module's OTEvent protobuf record (ot_event.proto); the
# module fills all 18 fields, so Zerobus rejects the stream if a column is missing.
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ignition} (
  event_id            STRING    COMMENT 'Unique event ID set by the module',
  event_time          TIMESTAMP COMMENT 'Tag value timestamp at the gateway (UTC)',
  tag_path            STRING    COMMENT 'Full Ignition tag path, e.g. [default]PLANT-A/PUMP-101/Vibration',
  tag_provider        STRING    COMMENT 'Ignition tag provider, e.g. default',
  numeric_value       DOUBLE    COMMENT 'Value of a numeric tag (0.0 for other types)',
  string_value        STRING    COMMENT 'Value of a string tag',
  boolean_value       BOOLEAN   COMMENT 'Value of a boolean tag',
  quality             STRING    COMMENT 'Ignition quality, e.g. Good',
  quality_code        INT       COMMENT '192 when the quality is good, else 0',
  source_system       STRING    COMMENT 'Source System ID set in the module',
  ingestion_timestamp BIGINT    COMMENT 'When the module captured the event (microseconds since the epoch)',
  data_type           STRING    COMMENT 'DOUBLE, STRING or BOOLEAN',
  alarm_state         STRING,
  alarm_priority      INT,
  sdt_compressed      BOOLEAN   COMMENT 'Emitted through swinging-door compression',
  compression_ratio   DOUBLE    COMMENT 'Swinging-door suppression percentage (0-100)',
  sdt_enabled         BOOLEAN,
  batch_bytes_sent    BIGINT
)
COMMENT 'Landing: raw tag events from the Ignition Zerobus Connector module, mapped into pump_tags_bronze by the silver pipeline'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")

# COMMAND ----------

for statement in (
    f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp}`",
    f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{sp}`",
    f"GRANT MODIFY, SELECT ON TABLE {bronze} TO `{sp}`",
    f"GRANT MODIFY, SELECT ON TABLE {ignition} TO `{sp}`",
):
    spark.sql(statement)
    print(statement)

# COMMAND ----------

# The HMI app reads bronze and silver. Granting SELECT on the schema also covers the
# silver table, which the pipeline creates later.
if app_name:
    from databricks.sdk import WorkspaceClient

    app_sp = WorkspaceClient().apps.get(app_name).service_principal_client_id
    for statement in (
        f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{app_sp}`",
        f"GRANT USE SCHEMA, SELECT ON SCHEMA `{catalog}`.`{schema}` TO `{app_sp}`",
    ):
        spark.sql(statement)
        print(statement)
