import { fmt } from "../severity.js";

const ROWS = [
  ["Running", "Run status", 0],
  ["MotorSpeed", "Speed", 0],
  ["MotorCurrent", "Motor current", 1],
  ["FlowRate", "Flow", 1],
  ["SuctionPressure", "Suction pressure", 2],
  ["DischargePressure", "Discharge pressure", 2],
  ["BearingTemp", "Bearing temperature", 1],
  ["Vibration", "Vibration", 2],
];

// One row per tag in the silver current-state table, with quality and age of the reading.
export default function TagTable({ tags, now }) {
  return (
    <div className="panel tags">
      <div className="panel-title">Silver · pump_tags_current</div>
      <table>
        <thead>
          <tr>
            <th>Tag</th>
            <th>Value</th>
            <th>Quality</th>
            <th className="age">Age</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([name, label, decimals]) => {
            const tag = tags[name];
            const age = tag?.event_ts ? (now - Date.parse(tag.event_ts)) / 1000 : null;
            const value = name === "Running" ? (tag ? (tag.value >= 0.5 ? "RUNNING" : "STOPPED") : "--") : fmt(tag?.value, decimals);
            return (
              <tr key={name}>
                <td>{label}</td>
                <td className="num">
                  {value} {name !== "Running" && tag ? <span className="muted">{tag.unit}</span> : null}
                </td>
                <td className={tag && tag.quality !== "GOOD" ? "bad" : ""}>{tag?.quality ?? "--"}</td>
                <td className="age">{age == null ? "--" : `${Math.max(0, age).toFixed(0)} s`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
