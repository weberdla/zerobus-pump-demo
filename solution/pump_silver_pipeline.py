"""Silver layer for the Zerobus pump demo (Lakeflow Spark Declarative Pipeline).

Reads the Change Data Feed (CDF) of the Zerobus bronze table and uses AUTO CDC to
maintain a current-state table: one row per (equipment_id, tag_name) holding the
latest reading (SCD Type 1).
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Set `bronze_table` under pipeline Settings > Configuration, or edit the default.
BRONZE_TABLE = spark.conf.get("bronze_table", "main.zerobus_lab.pump_tags_bronze")


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
