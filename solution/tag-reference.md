# Tag reference: PUMP-101 centrifugal pump

The simulator (`pump_simulator.py`) models one centrifugal pump, **PUMP-101** at site **PLANT-A**, driven
by motor **M-101**. Every second it writes one reading for each of the eight tags below. Each reading is
one row in the bronze table `pump_tags_bronze`, and the silver table `pump_tags_current` keeps the
latest reading of each tag. The plant screen labels the tags with ISA-style instrument numbers.
[Table structure and Zerobus records](#table-structure-and-zerobus-records) shows the tables and the
record the simulator sends.

## Tags

- **Range of values:** every value the tag can take: pump stopped, running healthy, or with a fully
  developed fault.
- **Normal operating range:** a healthy pump running at steady state. It covers the middle 98% of
  readings from a 30-minute healthy run.
- **Unit:** exactly as stored in the `unit` column.

| Tag (`tag_name`) | On screen | Description | Unit | Range of values | Normal operating range |
|------------------|-----------|-------------|------|-----------------|------------------------|
| `Running` | Run light on M-101 | Motor run status: 1 = running, 0 = stopped | `bool` | 0 or 1 | 1 |
| `MotorSpeed` | SI-101 | Speed of the motor and pump shaft; rated speed is 1,780 rpm | `rpm` | 0 – 1,786 | 1,775 – 1,785 |
| `MotorCurrent` | II-101 | Current drawn by the motor; rises and falls with flow | `A` | 0 – 42 | 33 – 41 |
| `FlowRate` | FI-101 | Flow out of the pump. Demand swings ±10% over a 10-minute cycle; the best efficiency point is 120 m³/h | `m3/h` | 0 – 117 | 89 – 115 |
| `SuctionPressure` | PI-101 | Pressure at the pump inlet, fed from tank T-100 | `bar` | 0.3 – 1.3 | 1.15 – 1.25 |
| `DischargePressure` | PI-102 | Pressure at the pump outlet; falls slightly as flow rises | `bar` | 1.1 – 6.7 | 6.0 – 6.6 |
| `BearingTemp` | TI-101 | Temperature of the drive-end bearing; lags changes in load by about 2 minutes | `degC` | 43 – 81 | 54.8 – 55.2 |
| `Vibration` | VI-101 | Vibration velocity at the bearing housing | `mm/s` | 0 – 8.2 | 1.8 – 2.1 |

## Alarm limits

The plant screen raises these alarms from the silver values. The alarm stays up for as long as the
reading is past the limit. The dashboard's pump health uses the same vibration and bearing-temperature
limits.

| Tag | WARNING | ALARM | Raised by |
|-----|---------|-------|-----------|
| `Vibration` | > 4.5 mm/s | > 7.1 mm/s | A bearing fault. Cavitation also causes spikes above 4.5 mm/s. |
| `BearingTemp` | > 65 °C | > 75 °C | A bearing fault, a minute or two after vibration |
| `SuctionPressure` | < 0.8 bar | < 0.5 bar | Cavitation; only checked while the pump runs |

When a run starts, you choose when the fault raises its first WARNING and ALARM. See step 3,
[Run the demo](README.md#3-run-the-demo), in the instructor guide.

## How the faults move the tags

Values for a fully developed fault, with the pump running. Tags not listed stay in their normal range.

| Tag | Bearing fault | Cavitation |
|-----|---------------|------------|
| `Vibration` | Rises steadily to about 8 mm/s | Spiky, 1.8 – 6 mm/s |
| `BearingTemp` | Rises to about 80 °C | Normal |
| `SuctionPressure` | Normal | Falls to about 0.4 bar |
| `FlowRate` | Normal | Falls by up to 30%, to about 60 – 72 m³/h |
| `MotorCurrent` | Normal | Falls with flow, to about 25 – 29 A |
| `DischargePressure` | Normal | Slightly lower, about 5.9 – 6.1 bar |

## Table structure and Zerobus records

### Bronze table: `pump_tags_bronze`

Zerobus Ingest writes each reading straight into this Delta table, one row per reading. The demo job's
first task creates it (`create_bronze.py`). Change Data Feed lets the silver pipeline read new rows
as a stream of changes.

```sql
CREATE TABLE IF NOT EXISTS <catalog>.zerobus_pump_demo.pump_tags_bronze (
  equipment_id STRING    COMMENT 'Asset ID, e.g. PUMP-101',
  site         STRING    COMMENT 'Plant or site code',
  tag_name     STRING    COMMENT 'Tag (signal) name, e.g. DischargePressure',
  value        DOUBLE    COMMENT 'Reading in engineering units; NULL when quality is BAD',
  unit         STRING    COMMENT 'Engineering unit, e.g. bar, rpm, degC',
  quality      STRING    COMMENT 'OPC UA-style quality: GOOD, UNCERTAIN, BAD',
  event_ts     TIMESTAMP COMMENT 'Scan time at the source (UTC)'
)
COMMENT 'Bronze: raw pump tag readings streamed in by Zerobus Ingest'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
```

### The record sent to Zerobus

The simulator sends each reading as a JSON record, with one field for each bronze column. Zerobus
matches fields to columns by name.

| Field | JSON type | Column type | Example | Notes |
|-------|-----------|-------------|---------|-------|
| `equipment_id` | string | `STRING` | `"PUMP-101"` | |
| `site` | string | `STRING` | `"PLANT-A"` | |
| `tag_name` | string | `STRING` | `"Vibration"` | One of the eight tags above |
| `value` | number or `null` | `DOUBLE` | `1.842` | Rounded to three decimal places; `null` when `quality` is `BAD` |
| `unit` | string | `STRING` | `"mm/s"` | As in the tags table |
| `quality` | string | `STRING` | `"GOOD"` | The simulator sends `GOOD` or `BAD` |
| `event_ts` | integer | `TIMESTAMP` | `1793718000000000` | Microseconds since the Unix epoch, UTC. All eight records in a scan share it. |

One record, the vibration reading of a scan at 15:00:00 UTC on 3 November 2026:

```json
{"equipment_id": "PUMP-101", "site": "PLANT-A", "tag_name": "Vibration", "value": 1.842,
 "unit": "mm/s", "quality": "GOOD", "event_ts": 1793718000000000}
```

### Sending the records

The simulator uses the Zerobus Ingest Python SDK, `databricks-zerobus-ingest-sdk` 1.10.0. A stream
opened with just the table name takes JSON records; the SDK also accepts Protobuf or Avro records
if you pass a schema in `TableProperties`. The stream authenticates as the demo's service principal,
which has `USE CATALOG`, `USE SCHEMA`, and `MODIFY` and `SELECT` on the bronze table.

```python
from zerobus.sdk.shared import TableProperties
from zerobus.sdk.sync import ZerobusSdk

# server_endpoint: https://<workspace-id>.zerobus.<region>.cloud.databricks.com
sdk = ZerobusSdk(server_endpoint, workspace_url, application_name="zerobus-pump-demo/1.0")
stream = sdk.create_stream(client_id, client_secret,
                           TableProperties("<catalog>.zerobus_pump_demo.pump_tags_bronze"))

stream.ingest_records_offset(records)  # one scan: a list of eight records like the one above
stream.flush()                         # waits until everything sent so far is durable in the table
stream.close()                         # flushes anything still in flight
```

The simulator sends a scan every second and flushes every 10 scans. Zerobus delivers each record at
least once, so a retry can write a reading twice. Silver handles that: a duplicate has the same key
and timestamp as the reading it repeats.

### Sending readings from another source

With the simulator off (see [Use another data feed](README.md#use-another-data-feed) in the instructor
guide), another source such as Ignition sends the readings. For the plant screen and the dashboard to
show them:

- **Destination:** the same Zerobus endpoint, `https://<workspace-id>.zerobus.<region>.cloud.databricks.com`,
  and bronze table, with records in the format above.
- **`equipment_id`:** `PUMP-101`. The plant screen only reads that equipment. `site` can be any value.
- **Tags:** the tag names and units in the [tags table](#tags). The screen only shows those names.
  Send all eight, including `Running` with the value 1, or the screen shows the pump stopped.
- **Quality:** `GOOD`, with a value. Silver drops readings without a value.
- **`event_ts`:** when the reading was taken, in microseconds since the Unix epoch, UTC. The screen only
  shows readings taken after the run started, and AUTO CDC keeps each tag's newest reading.
- **Timing:** start sending once the run says it's waiting for the external feed. The run creates the
  bronze table if it doesn't exist; destroying the bundle drops it.
- **Credentials:** a service principal with `USE CATALOG` on the catalog, `USE SCHEMA` on the schema,
  and `MODIFY` and `SELECT` on the bronze table. You can use the demo's, `zerobus-pump-demo-simulator`,
  whose credentials are in the secret scope `zerobus-pump-demo`, or grant your own:

  ```sql
  GRANT USE CATALOG ON CATALOG <catalog> TO `<application-id>`;
  GRANT USE SCHEMA ON SCHEMA <catalog>.zerobus_pump_demo TO `<application-id>`;
  GRANT MODIFY, SELECT ON TABLE <catalog>.zerobus_pump_demo.pump_tags_bronze TO `<application-id>`;
  ```

  Revoke your own principal's grants when you're done; the cleanup script only handles the demo's.

- **From the Ignition Zerobus Connector module:** send to `<catalog>.zerobus_pump_demo.ignition_events_bronze` instead.
  The silver pipeline maps the module's records into bronze; see
  [Ignition with the Zerobus Connector module](README.md#ignition-with-the-zerobus-connector-module).

  | Module field | Bronze column |
  |--------------|---------------|
  | `tag_path` `[provider]<site>/<equipment_id>/<tag_name>` | `site`, `equipment_id`, `tag_name` |
  | `numeric_value` (`boolean_value` for boolean tags) | `value`, rounded to three decimal places; `null` when the quality is bad |
  | — | `unit`, from the tags table |
  | `quality` (`Good`, `Bad_…`, `Uncertain_…`) | `quality`: `GOOD`, `BAD` or `UNCERTAIN` |
  | `event_time` | `event_ts` |

### Silver table: `pump_tags_current`

The silver pipeline keeps one row per tag, the latest reading, with AUTO CDC (SCD Type 1). It has the
bronze columns plus one more.

| Column | Type | Notes |
|--------|------|-------|
| `equipment_id`, `tag_name` | `STRING` | The key: one row per tag of each pump |
| `site`, `value`, `unit`, `quality`, `event_ts` | As in bronze | From the tag's newest reading by `event_ts`. A late, older reading never overwrites a newer one. |
| `bronze_committed_at` | `TIMESTAMP` | When the reading was committed to bronze |

## Readings and quality

- About 0.5% of readings are sensor dropouts: `quality` is `BAD` and `value` is empty. They land in
  bronze, but the silver pipeline drops readings with no value, so silver keeps the tag's last good
  reading. The pipeline's data quality metrics count them.
- The demo keeps the pump running. The simulator can also stop the pump for 30 – 60 seconds every
  5 – 10 minutes. During a stop, `Running` reads 0; speed, flow, current, and vibration fall to about zero;
  discharge pressure falls to the suction pressure; and the bearing cools toward the 25 °C ambient
  temperature, to about 43 °C in a one-minute stop.
