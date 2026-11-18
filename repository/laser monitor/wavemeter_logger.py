from artiq.experiment import *
import csv
import os
import time
from datetime import datetime, timezone


class WavemeterLogger(EnvExperiment):
    """Wavemeter logger"""

    def build(self):
        self.setattr_device("wavemeter")
        self.setattr_device("ccb")
        self.setattr_device("scheduler")
        self.setattr_argument("channels", StringValue("1, 2"),
                              tooltip="Wavemeter channels to log, comma separated")
        self.setattr_argument("poll_interval", NumberValue(1.0, min=0.1, step=0.1, unit="s"))
        self.setattr_argument("duration", NumberValue(0.0, min=0.0, step=60.0, unit="min", scale=60, precision=1),
                              tooltip="0 = run until terminated (Schedule panel -> right click -> Request termination)")
        self.setattr_argument("plot_window", NumberValue(3600, min=10, step=100, precision=0),
                              tooltip="Points kept in the live plots; the CSV keeps everything")

    def prepare(self):
        self.chs = [int(c) for c in self.channels.replace(",", " ").split()]
        if not self.chs or any(not 1 <= c <= 8 for c in self.chs):
            raise ValueError("channels must be wavemeter channels 1-8, e.g. '1, 2'")

    def _reset_plot(self, ch, t=None, offset=None):
        self.set_dataset("wavemeter.ch%d.t_min" % ch, t or [], broadcast=True, archive=False)
        self.set_dataset("wavemeter.ch%d.offset_mhz" % ch, offset or [], broadcast=True, archive=False)

    def run(self):
        output_dir = os.path.join(os.path.dirname(__file__), "..", "results", "wavemeter")
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.abspath(os.path.join(output_dir, "wavemeter_log_ch%s_%s.csv" % (
            "-".join(str(c) for c in self.chs), datetime.now().strftime("%Y%m%d_%H%M%S"))))

        window = int(self.plot_window)
        # first good reading of each channel; plots show the offset from it in MHz
        reference = {}
        points = {ch: ([], []) for ch in self.chs}
        for ch in self.chs:
            self._reset_plot(ch)
            # one applet per channel: the lasers can be far apart, so a shared axis would hide the drift
            self.ccb.issue("create_applet", "Ch%d" % ch,
                           "${artiq_applet}plot_xy wavemeter.ch%d.offset_mhz --x wavemeter.ch%d.t_min"
                           " --title {wavemeter/ch%d/title}" % (ch, ch, ch),
                           group="wavemeter")

        print("Logging channels %s every %.1f s" % (self.chs, self.poll_interval))
        print("Saving to: %s" % filename)

        start = time.monotonic()
        stop_at = start + self.duration if self.duration > 0 else None
        count = 0
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["timestamp_utc"] + ["ch%d_frequency_THz" % ch for ch in self.chs])
            while not self.scheduler.check_termination():
                now = time.monotonic()
                if stop_at is not None and now >= stop_at:
                    break
                t_min = (now - start) / 60
                row = [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]]
                for ch in self.chs:
                    freq = self.wavemeter.get_frequency(ch)
                    if not isinstance(freq, float):
                        # error string such as "Low signal": logged, but not plotted
                        row.append(freq)
                        continue
                    row.append("%.7f" % freq)
                    self.set_dataset("wavemeter.ch%d.frequency" % ch, freq, broadcast=True, archive=False)
                    if ch not in reference:
                        reference[ch] = freq
                        self.set_dataset("wavemeter.ch%d.title" % ch,
                                         "Ch%d: offset from %.7f THz (MHz) vs time (min)" % (ch, freq),
                                         broadcast=True, archive=False)
                    offset = (freq - reference[ch]) * 1e6
                    t, y = points[ch]
                    t.append(t_min)
                    y.append(offset)
                    if len(t) > window * 5 // 4:
                        # trim in batches so most updates stay small appends
                        del t[:-window], y[:-window]
                        self._reset_plot(ch, t, y)
                    else:
                        self.append_to_dataset("wavemeter.ch%d.t_min" % ch, t_min)
                        self.append_to_dataset("wavemeter.ch%d.offset_mhz" % ch, offset)
                writer.writerow(row)
                csvfile.flush()
                count += 1
                # sleep in short steps so termination is noticed quickly at long intervals
                next_poll = now + self.poll_interval
                while time.monotonic() < next_poll and not self.scheduler.check_termination():
                    time.sleep(min(0.2, max(0.0, next_poll - time.monotonic())))

        print("Stopped. %d readings saved to %s" % (count, filename))
