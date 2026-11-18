import json
import subprocess

from artiq.experiment import *


# The oven is powered by a BK Precision 1685B on COM3 of the Windows PC "Testbed".
# This experiment runs on the host only (no kernel): it pipes a small pyserial script
# over SSH to that PC. Close the BK oven software first, or COM3 is "Access is denied".
SSH_USER = "Testbed PC"
SSH_HOST = "testbed.bham.ac.uk"
# Used only if SSH_HOST can't be looked up (this PC gets DNS only via Wi-Fi). SSH still checks
# the host key stored for SSH_HOST, so a different machine at this address is refused.
SSH_FALLBACK_IP = "172.29.13.47"

# Highest current this experiment will set. Raise it only to a current the oven can take.
MAX_CURRENT_SETPOINT = 1.50  # A
# after On/Off the measured current must be this close to the setpoint (On) or to 0 (Off),
# otherwise the run fails, which the lab alert watcher reports
CURRENT_READBACK_TOLERANCE = 0.10  # A

# Runs on the Windows PC. Commands are from the 1685B programming manual:
# 9600 8N1, CR-terminated, replies end in "OK\r"; SOUT0 = output ON, SOUT1 = output OFF.
REMOTE_SCRIPT = r"""
import json, sys, time
import serial

action, max_current, new_current = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
if not 0.0 <= new_current <= max_current:
    raise SystemExit("current {} A is outside 0-{} A; nothing sent".format(new_current, max_current))

try:
    port = serial.Serial("COM3", 9600, bytesize=8, parity="N", stopbits=1, timeout=1)
except serial.SerialException as e:
    if "Access is denied" not in str(e):
        raise
    raise SystemExit("COM3 is in use, probably by the BK oven software. Close it and try again; nothing was sent.")

with port:
    port.reset_input_buffer()

    def query(cmd):
        port.write((cmd + "\r").encode())
        reply = port.read_until(b"OK\r")
        if not reply.endswith(b"OK\r"):
            raise RuntimeError("no reply to " + cmd + " (is the supply on and in Normal mode?)")
        return reply.split(b"\r")[0].decode()

    # 1685B current has two decimal places: CURR150 = 1.50 A
    set_current = "CURR{:03d}".format(round(new_current * 100))
    if action == "On":
        # set the current first, so the output never comes on at an old setpoint
        query(set_current)
        query("SOUT0")
    elif action == "Off":
        # switch off first, then store the current for the next "On"
        query("SOUT1")
        query(set_current)
    elif action != "Status":
        # Status only reads the setpoints and readings below
        raise SystemExit("unknown action " + action)
    if action != "Status":
        time.sleep(2)

    s = query("GETS")
    d = query("GETD")
    result = {"voltage_setpoint": int(s[0:3]) / 10, "current_setpoint": int(s[3:6]) / 100,
              "voltage": int(d[0:4]) / 100, "current": int(d[4:8]) / 100,
              "mode": "CC" if d[8] == "1" else "CV"}

print(json.dumps(result))
"""


class OvenControl(EnvExperiment):
    """Oven control"""

    def build(self):
        self.setattr_argument("current", NumberValue(default=1.20, unit="A", min=0.0, max=MAX_CURRENT_SETPOINT,
                                                     precision=2, step=0.01),
                              tooltip="Applied when On or Off is pressed (Status ignores it). To change the current "
                                      "while the oven is on, enter the new value and press On.")
        # quickstyle: shown as buttons that submit the experiment immediately when clicked
        self.setattr_argument("output", EnumerationValue(["Status", "On", "Off"], default="Status", quickstyle=True))

    def _ssh(self, host, *ssh_options):
        return subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *ssh_options, SSH_USER + "@" + host,
             "python", "-", self.output, str(MAX_CURRENT_SETPOINT), "{:.2f}".format(self.current)],
            input=REMOTE_SCRIPT, capture_output=True, text=True, timeout=60)

    def run(self):
        proc = self._ssh(SSH_HOST)
        if proc.returncode != 0 and "Could not resolve hostname" in proc.stderr:
            # name lookup failed, so nothing reached the PC; safe to retry by address
            print("Could not look up {}; retrying via {}".format(SSH_HOST, SSH_FALLBACK_IP))
            proc = self._ssh(SSH_FALLBACK_IP, "-o", "HostKeyAlias=" + SSH_HOST)
        if proc.returncode != 0:
            raise RuntimeError("oven command failed:\n" + (proc.stderr.strip() or proc.stdout.strip()))

        result = json.loads(proc.stdout.strip().splitlines()[-1])
        for key, value in result.items():
            self.set_dataset("oven." + key, value, broadcast=True)
        print("Oven {}: {:.2f} V, {:.2f} A ({}); setpoints {:.1f} V, {:.2f} A".format(
            "status" if self.output == "Status" else self.output, result["voltage"], result["current"], result["mode"],
            result["voltage_setpoint"], result["current_setpoint"]))

        expected = {"On": self.current, "Off": 0.0}.get(self.output)
        if expected is not None and abs(result["current"] - expected) > CURRENT_READBACK_TOLERANCE:
            raise RuntimeError("oven reads {:.2f} A ({}) after {}, expected {:.2f} A: check the oven wiring and "
                               "the supply".format(result["current"], result["mode"], self.output, expected))
