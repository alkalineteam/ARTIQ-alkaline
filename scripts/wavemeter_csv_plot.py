#!/usr/bin/env python3
"""
Live plot of a wavemeter CSV log, redrawn as the file grows.

Reads both log formats in repository/results/wavemeter:
  wavemeter_log_*.csv  (WavemeterLogger: timestamp_utc, ch1_frequency_THz, ch2_frequency_THz, ...)
  freq_log_*.csv       (FreqLogger:      timestamp_utc, channel, frequency_THz)

Each channel gets its own panel, showing the offset in MHz from that
channel's lockpoint in LOCKPOINTS, or from its first reading if it has none.
Error readings ("Low signal" etc.) are skipped.

Usage:
    python3 scripts/wavemeter_csv_plot.py              # newest CSV in results/wavemeter
    python3 scripts/wavemeter_csv_plot.py some_log.csv
"""

import argparse
import csv
import glob
import os
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "repository", "results", "wavemeter")

# plot reference only (THz); the wavemeter's own lock setpoints are not touched
LOCKPOINTS = {
    1: 650.503714,  # 461 BMOT
    2: 650.503660,
}


class CsvTail:
    """Reads only the complete lines added to the CSV since the last call."""

    def __init__(self, path):
        self.f = open(path, newline="")
        self.header = next(csv.reader([self.f.readline()]))
        self.partial = ""

    def new_rows(self):
        text = self.partial + self.f.read()
        lines = text.split("\n")
        # the last piece may be a row the logger is still writing
        self.partial = lines.pop()
        return list(csv.reader(line for line in lines if line.strip()))


def parse_rows(header, rows):
    """Yield (channel, time, frequency_THz) for every valid reading."""
    for row in rows:
        try:
            t = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).astimezone()
        except (ValueError, IndexError):
            continue
        if header[1] == "channel":
            pairs = [(row[1], row[2])]
        else:
            # "ch1_frequency_THz" -> "1"
            pairs = [(name[2:].split("_")[0], value) for name, value in zip(header[1:], row[1:])]
        for ch, value in pairs:
            try:
                yield int(ch), t, float(value)
            except ValueError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Live plot of a wavemeter CSV log")
    parser.add_argument("csv", nargs="?", help="CSV file (default: newest in %s)" % LOG_DIR)
    parser.add_argument("--interval", type=float, default=1.0, help="refresh interval in s (default: %(default)s)")
    args = parser.parse_args()

    path = args.csv
    if path is None:
        logs = glob.glob(os.path.join(LOG_DIR, "*.csv"))
        if not logs:
            raise SystemExit("no CSV files in " + LOG_DIR)
        path = max(logs, key=os.path.getmtime)
    print("Plotting " + path)

    tail = CsvTail(path)
    if tail.header[1] == "channel":
        # FreqLogger files hold one channel; its number is in the rows
        channels = None
    else:
        channels = [int(name[2:].split("_")[0]) for name in tail.header[1:]]

    data = {}  # channel -> (times, offsets_mhz, reference_THz)
    fig = plt.figure(os.path.basename(path), figsize=(10, 6))

    def update(_frame):
        for ch, t, freq in parse_rows(tail.header, tail.new_rows()):
            if ch not in data:
                data[ch] = ([], [], LOCKPOINTS.get(ch, freq))
            times, offsets, ref = data[ch]
            times.append(t)
            offsets.append((freq - ref) * 1e6)

        chs = channels or sorted(data)
        fig.clear()
        axes = fig.subplots(len(chs), 1, sharex=True, squeeze=False)[:, 0] if chs else []
        for ax, ch in zip(axes, chs):
            if ch in data:
                times, offsets, ref = data[ch]
                ax.plot(times, offsets, ".-", ms=3, lw=0.8)
                ax.axhline(0, color="k", lw=0.8, alpha=0.5)
                ax.set_title("Ch%d: offset from %s %.6f THz, latest %+.2f MHz" % (
                    ch, "lockpoint" if ch in LOCKPOINTS else "first reading", ref, offsets[-1]), fontsize=10)
            else:
                ax.set_title("Ch%d: no valid readings yet" % ch, fontsize=10)
            ax.set_ylabel("MHz")
            ax.grid(True, alpha=0.3)
        if len(axes):
            axes[-1].set_xlabel("local time")
            axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.tight_layout()

    # keep a reference, or the animation is garbage collected and stops
    anim = animation.FuncAnimation(fig, update, interval=args.interval * 1000, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()
