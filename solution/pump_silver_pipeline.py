"""Silver layer for the Zerobus pump demo (Lakeflow Spark Declarative Pipeline).

Reads the Change Data Feed (CDF) of the Zerobus bronze table and uses AUTO CDC to
maintain a current-state table: one row per (equipment_id, tag_name) holding the
latest reading (SCD Type 1).

When `ignition_table` is set, the pipeline also maps tag events from the Ignition Zerobus
Connector module (its own fixed record format) into the bronze table, so a live Ignition
gateway can feed the demo instead of the simulator.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Set `bronze_table` under pipeline Settings > Configuration, or edit the default.
BRONZE_TABLE = spark.conf.get("bronze_table", "main.zerobus_lab.pump_tags_bronze")
# Landing table of the Ignition Zerobus Connector module. Empty = no Ignition flow.
IGNITION_TABLE = spark.conf.get("ignition_table", "")

# Ignition rows older than this when the pipeline first reads them are skipped, so leftovers from
# an earlier run don't replay into bronze when the pipeline starts.
IGNITION_MAX_AGE_MINUTES = int(spark.conf.get("ignition_max_age_minutes", "5"))

# tag_name -> unit, as in the tag reference (and pump_simulator.TAGS). Ignition tags outside this
# list are not mapped: the plant screen only knows these eight.
PUMP_TAG_UNITS = {
    "Running": "bool",
    "MotorSpeed": "rpm",
    "MotorCurrent": "A",
    "FlowRate": "m3/h",
    "SuctionPressure": "bar",
    "DischargePressure": "bar",
    "BearingTemp": "degC",
    "Vibration": "mm/s",
}

# Ignition tag path layout: [provider]<site>/<equipment_id>/<tag_name>,
# e.g. [default]PLANT-A/PUMP-101/Vibration.
IGNITION_TAG_PATH = r"^\[[^\]]*\]([^/]+)/([^/]+)/([^/]+)$"

if IGNITION_TABLE:
    # The bronze table is created by the demo job (create_bronze.py), not by this pipeline,
    # so the Ignition flow writes to it through a Delta sink.
    dp.create_sink(name="pump_tags_bronze_sink", format="delta", options={"tableName": BRONZE_TABLE})

    @dp.append_flow(target="pump_tags_bronze_sink", name="ignition_to_bronze",
                    comment="Ignition Zerobus Connector events mapped to the bronze reading format")
    def ignition_to_bronze():
        units = F.create_map(*[F.lit(x) for pair in PUMP_TAG_UNITS.items() for x in pair])
        quality = F.upper(F.coalesce(F.col("quality"), F.lit("")))
        quality = (F.when(quality.startswith("GOOD"), "GOOD")
                   .when(quality.startswith("BAD") | quality.startswith("ERROR"), "BAD")
                   .otherwise("UNCERTAIN"))
        return (
            spark.readStream.table(IGNITION_TABLE)
            .where(F.col("event_time") >= F.expr(f"current_timestamp() - INTERVAL {IGNITION_MAX_AGE_MINUTES} MINUTES"))
            .select(
                F.regexp_extract("tag_path", IGNITION_TAG_PATH, 2).alias("equipment_id"),
                F.regexp_extract("tag_path", IGNITION_TAG_PATH, 1).alias("site"),
                F.regexp_extract("tag_path", IGNITION_TAG_PATH, 3).alias("tag_name"),
                # Booleans arrive with numeric_value 0.0, so fall back to boolean_value for them.
                F.when(F.col("data_type") == "BOOLEAN", F.col("boolean_value").cast("double"))
                 .otherwise(F.col("numeric_value")).alias("raw_value"),
                quality.alias("quality"),
                F.col("event_time").alias("event_ts"),
            )
            .where(F.col("tag_name").isin(list(PUMP_TAG_UNITS)))
            .select(
                "equipment_id",
                "site",
                "tag_name",
                # As with the simulator: a BAD reading has no value, and silver drops it.
                F.when(F.col("quality") == "BAD", F.lit(None).cast("double"))
                 .otherwise(F.round("raw_value", 3)).alias("value"),
                units[F.col("tag_name")].alias("unit"),
                "quality",
                "event_ts",
            )
        )



@dp.temporary_view(comment="Bronze change feed: new and corrected rows only")
@dp.expect_or_drop("value_present", "value IS NOT NULL")
@dp.expect("quality_good", "quality = 'GOOD'")
def pump_tags_changes():
    return (
        spark.readStream
        .option("readChangeFeed", "true")
        .table(BRONZE_TABLE)
        # Zerobus appends rows (insert). UPDATEs on bronze add update_postimage rows.
        # Deletes (e.g. retention purges) are ignored so silver keeps the latest value.
        .where(F.col("_change_type").isin("insert", "update_postimage"))
        .withColumnRenamed("_commit_timestamp", "bronze_committed_at")
    )


dp.create_streaming_table(
    name="pump_tags_current",
    comment="Latest reading per pump tag (SCD Type 1), maintained from bronze CDF by AUTO CDC",
)

dp.create_auto_cdc_flow(
    target="pump_tags_current",
    source="pump_tags_changes",
    keys=["equipment_id", "tag_name"],
    # Newest source timestamp wins; for equal timestamps the later bronze commit
    # (e.g. a correction) wins. Late, older readings never overwrite newer ones.
    sequence_by=F.struct("event_ts", "_commit_version"),
    except_column_list=["_change_type", "_commit_version"],
    stored_as_scd_type=1,
)
