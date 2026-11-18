
# Device database for the SM18-220 experiment (Delta Elektronika coil supply).
#
# TODO: this experiment's Kasli. Put its crate JSON in crate_config/ and generate
# the hardware section with artiq_ddb_template. Until then only the core device
# and the NDSP controllers are listed. core_addr is a placeholder that never
# resolves (.invalid), so nothing on this branch can reach the testbed Kasli.
core_addr = "kasli.invalid"

device_db = {
    "core": {
        "type": "local",
        "module": "artiq.coredevice.core",
        "class": "Core",
        "arguments": {
            "host": core_addr,
            "ref_period": 1e-09,
            "target": "rv32g",  # TODO: check against this experiment's Kasli
            "satellite_cpu_targets": {},
        },
    },
    "core_log": {
        "type": "controller",
        "host": "::1",
        "port": 1068,
        "command": "aqctl_corelog -p {port} --bind {bind} " + core_addr
    },
    "core_cache": {
        "type": "local",
        "module": "artiq.coredevice.cache",
        "class": "CoreCache"
    },
    "core_dma": {
        "type": "local",
        "module": "artiq.coredevice.dma",
        "class": "CoreDMA"
    },
}

# --- NDSP controllers (ARTIQ-alkaline) ---
# Delta Elektronika SM18-220 power supply (NDSP controller, SCPI over Ethernet, port 8462).
# TODO: set the supply's IP here and as SM18220_IP in flake.nix; the two must match.
sm18220_ip = "TODO"
device_db["sm18220"] = {
    "type": "controller",
    "host": "::1",
    "port": 3291,
    "command": "python3 /home/artiq/ARTIQ-alkaline/ndsp_config/aqctl_sm18220.py -p {port} --bind {bind} --ip " + sm18220_ip
}
