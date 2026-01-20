from(bucket: "experiments")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "clock_transition")
  // Automatically find the latest run
  |> group(columns: ["run_id"])
  |> max(column: "_time")
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
  |> findColumn(fn: (key) => true, column: "run_id")
  // Filter for it
  |> yield(name: "latest_run_id")

// Now get the data for that run
from(bucket: "experiments")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "clock_transition")
  // Use the ID we just found (you might need to use a variable for this part normally, but simpler:)
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> drop(columns: ["_start", "_stop", "_time"])