# andor-ndsp

Standalone ARTIQ NDSP controller for **Andor SDK3 (sCMOS)** cameras
(Zyla / Neo / Sona / Marana), exposing the camera over sipyco RPC.

It is meant to run on the **Windows acquisition PC** (where the Andor SDK and
camera live) and bind to the network so an ARTIQ master on another machine
reaches it over Ethernet. A `--simulation` mode serves synthetic frames so you
can test with no camera or SDK installed.

This is a single self-contained script — `aqctl_andor.py` imports only
`sipyco`, `numpy` and (for real hardware) `pylablib`.

## Requirements

- Python **3.10+** (3.13 recommended; 3.6 will NOT work — `sipyco`/`numpy` need 3.9+).
- `sipyco`, `numpy`, `pylablib` (see `requirements.txt`).
- For real hardware only: the **Andor SDK3 runtime** (`atcore` DLLs), from Andor
  Solis or the standalone SDK3 installer.

## Setup (Windows)

```powershell
git clone <this-repo-url> andor-ndsp
cd andor-ndsp
py -3.13 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run

Simulation (no camera/SDK needed — good first test):

```powershell
run_andor.bat --simulation
```

Real camera:

```powershell
run_andor.bat
```

`run_andor.bat` binds to all interfaces (`--bind "*"`), auto-restarts on exit,
and logs to `logs\andor.log`. Stop it by closing the window or Ctrl-C.

To run by hand instead of the launcher:

```powershell
.\.venv\Scripts\python aqctl_andor.py -p 3287 --bind "*" -v
```

## Verify it's reachable

On the same PC:

```powershell
.\.venv\Scripts\sipyco_rpctool ::1 3287 list-targets        # should list "andor"
```

From the ARTIQ (Linux) machine:

```bash
sipyco_rpctool <WINDOWS_IP> 3287 list-targets
```

Find `<WINDOWS_IP>` with `ipconfig`. If the Linux box can't connect, allow the
port through Windows Firewall (admin PowerShell):

```powershell
New-NetFirewallRule -DisplayName "ARTIQ Andor NDSP" -Direction Inbound -Protocol TCP -LocalPort 3287 -Action Allow
```

## Wire it into ARTIQ (on the master / Linux side)

Add the controller to the master's `device_db.py` (no `command` — it is started
manually here on Windows):

```python
device_db["andor"] = {
    "type": "controller",
    "host": "<WINDOWS_IP>",
    "port": 3287,
}
```

Then experiments can call it, e.g. `self.andor.snap()`, `self.andor.set_exposure(0.01)`.

## RPC methods (summary)

Info: `ping`, `is_simulation`, `get_device_info`, `get_detector_size`.
Exposure/timing: `get/set_exposure`, `get/set_frame_period`, `get_frame_timings`.
ROI: `get/set_roi`, `reset_roi`, `get_roi_limits`.
Trigger: `get/set_trigger_mode`.
Cooling: `is_cooler_on`, `set_cooler`, `get_temperature`, `get_temperature_setpoint`, `set_temperature`.
SDK3 attributes: `list_attributes`, `get/set_attribute`, plus `get/set_preamp_gain`,
`get/set_shutter_mode`, `get/set_readout_rate`.
Acquisition: `snap`, `start_live`, `stop_live`, `is_acquiring`, `get_latest_frame(downsample)`.
