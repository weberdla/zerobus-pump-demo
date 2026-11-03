# Databricks notebook source
# MAGIC %md
# MAGIC # Create the bronze table and grant access
# MAGIC
# MAGIC Creates the bronze table with Change Data Feed on, gives the Zerobus service principal
# MAGIC write access to it, and gives the HMI app's service principal read access to the schema.
# MAGIC Safe to re-run.

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

for statement in (
    f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp}`",
    f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{sp}`",
    f"GRANT MODIFY, SELECT ON TABLE {bronze} TO `{sp}`",
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
