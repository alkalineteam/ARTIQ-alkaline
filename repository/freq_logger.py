from artiq.experiment import *
import csv
import os
import time
from datetime import datetime, timezone
import numpy as np


class FreqLogger(EnvExperiment):

    def build(self):
        self.setattr_device("wavemeter")
        self.setattr_device("ccb")
        self.setattr_argument("channel", NumberValue(8, min=1, max=8, step=1, precision=0))
        self.setattr_argument("poll_interval", NumberValue(1.0, min=0.1, step=0.1, unit="s"))

    def run(self):
        ch = int(self.channel)
        output_dir = os.path.join(os.path.dirname(__file__), "results", "wavemeter")
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, "freq_log_ch%d_%s.csv" % (ch, datetime.now().strftime("%Y%m%d_%H%M%S")))

        # Create live frequency applet on the dashboard
        self.ccb.issue("create_applet",
                       "Frequency",
                       "${artiq_applet}plot_xy"
                       " wavemeter.ch%d.frequency" % ch
                       + " --title Frequency_THz",
                       group="wavemeter")

        print("Logging Channel %d | %.1f s interval" % (ch, self.poll_interval))
        print("Saving to: %s" % filename)
        print("Press Ctrl+C to stop.\n")

        count = 0
        freq_list = []
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["timestamp_utc", "channel", "frequency_THz"])

            try:
                while True:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    freq = self.wavemeter.get_frequency(ch)

                    if isinstance(freq, float) and freq > 0:
                        writer.writerow([now, ch, "%.6f" % freq])
                        freq_list.append(freq)
                        self.set_dataset("wavemeter.ch%d.frequency" % ch, np.array(freq_list), broadcast=True)
                    else:
                        writer.writerow([now, ch, str(freq)])

                    csvfile.flush()
                    count += 1
                    time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                pass

        print("\nStopped. %d readings saved to '%s'." % (count, filename))
