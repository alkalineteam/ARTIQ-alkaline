#!/usr/bin/env python3
"""
Standalone real-time interferometer pattern viewer.

Uses the wlmData library DIRECTLY (no RPC) to fetch pattern data
and displays it with matplotlib. Run this alongside freq_logger.

Usage:
    python3 scripts/interferometer_viewer.py --channel 8
"""

import argparse
import ctypes
import sys
import os
import time

# Add ndsp_config to path for wlmData module
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
NDSP_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "ndsp_config")
sys.path.insert(0, NDSP_DIR)
os.chdir(NDSP_DIR)  # wlmData.ini must be in CWD

import wlmData
import wlmConst

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

DEFAULT_DLL_PATH = "/usr/lib/libwlmData.so"


def get_pattern(channel, index):
    """Fetch interferometer pattern data directly from the DLL."""
    count = wlmData.dll.GetPatternItemCount(int(index))
    if count <= 0:
        return np.array([])
    # Use the correct item size — int16 for most wavemeters, int32 for some
    item_size = wlmData.dll.GetPatternItemSize(int(index))
    if item_size == 2:
        array = (ctypes.c_int16 * count)()
    else:
        array = (ctypes.c_int32 * count)()
    result = wlmData.dll.GetPatternDataNum(int(channel), int(index), ctypes.cast(array, ctypes.c_void_p))
    if result < 0:
        return np.array([])
    return np.array(array, dtype=np.int32)


def main():
    parser = argparse.ArgumentParser(description="Real-time interferometer pattern viewer")
    parser.add_argument("--channel", type=int, default=8, help="Wavemeter channel (default: 8)")
    parser.add_argument("--interval", type=int, default=200, help="Update interval in ms (default: 200)")
    parser.add_argument("--dll", default=DEFAULT_DLL_PATH, help="Path to libwlmData.so")
    args = parser.parse_args()

    # Load the DLL
    wlmData.LoadDLL(args.dll)
    print("Loaded wlmData library from %s" % args.dll)

    # Enable pattern acquisition
    wlmData.dll.SetPattern(1, 1)
    wlmData.dll.SetPattern(2, 1)
    print("Pattern acquisition enabled")

    # Set up matplotlib
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    fig.suptitle("Interferometer Patterns — Channel %d" % args.channel)
    line1, = ax1.plot([], [], linewidth=0.5)
    line2, = ax2.plot([], [], linewidth=0.5, color="tab:orange")
    ax1.set_title("Interferometer 1")
    ax2.set_title("Interferometer 2")
    ax1.set_ylabel("Intensity")
    ax2.set_ylabel("Intensity")
    ax2.set_xlabel("Pixel")

    def update(frame):
        p1 = get_pattern(args.channel, 1)
        p2 = get_pattern(args.channel, 2)

        if len(p1) > 0:
            line1.set_data(np.arange(len(p1)), p1)
            ax1.set_xlim(0, len(p1))
            ax1.set_ylim(p1.min() - 100, p1.max() + 100)

        if len(p2) > 0:
            line2.set_data(np.arange(len(p2)), p2)
            ax2.set_xlim(0, len(p2))
            ax2.set_ylim(p2.min() - 100, p2.max() + 100)

        return line1, line2

    ani = animation.FuncAnimation(fig, update, interval=args.interval, blit=False)
    plt.tight_layout()
    print("Displaying patterns (close window to stop)...")
    plt.show()


if __name__ == "__main__":
    main()
