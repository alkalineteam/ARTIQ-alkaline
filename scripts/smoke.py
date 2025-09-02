#!/usr/bin/env python3
"""Enhanced environment smoke test.

Run inside the nix develop shell:
    python scripts/smoke.py

Checks performed:
  - Imports and versions of core packages (artiq, torch, ndscan, oitg, qasync)
  - CUDA availability and simple GPU tensor operation
  - qasync + PyQt6 minimal event loop (offscreen) coroutine execution
  - ndscan basic attribute presence (sanity heuristic)
  - Environment variable sanity (VIRTUAL_ENV, PYTHONPATH not manually polluted)

Exits non‑zero on any failure. Designed to be fast (<1s if GPU warm).
"""

from __future__ import annotations
import importlib, os, sys, traceback, textwrap, time

# Early guidance: if not inside the Nix dev shell, most imports will fail.
if "VIRTUAL_ENV" not in os.environ and not os.environ.get("UV_PYTHON"):
    guess = None
    # Try to locate a Nix-provided virtualenv in the store (pattern *-artiq-fork-dev-env)
    store = "/nix/store"
    try:
        if os.path.isdir(store):
            for name in os.listdir(store):
                if name.endswith("-artiq-fork-dev-env"):
                    guess = os.path.join(store, name)
                    break
    except Exception:  # pragma: no cover - best effort only
        pass
    msg = [
        "[smoke] Warning: Not inside 'nix develop' shell (VIRTUAL_ENV unset).",
        "         Run either:",
        "           nix develop --impure",
        "           python scripts/smoke.py",
    ]
    if guess:
        msg.append(f"         Or invoke its python directly: {guess}/bin/python scripts/smoke.py")
    print("\n" + "\n".join(msg) + "\n")

RESULTS: list[tuple[str, bool, str]] = []

def record(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))

def import_and_version():
    packages = [
        ("artiq", "__version__"),
        ("torch", "__version__"),
        ("ndscan", "__version__"),
        ("oitg", None),
        ("qasync", None),
    ("sipyco", "__version__"),
    ]
    for name, attr in packages:
        try:
            mod = importlib.import_module(name)
            if attr and hasattr(mod, attr):
                record(f"import:{name}", True, getattr(mod, attr))
            else:
                record(f"import:{name}", True, "ok")
        except Exception as e:
            record(f"import:{name}", False, repr(e))

def cuda_test():
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            record("cuda:available", False, "cuda.is_available()==False")
            return
        start = time.time()
        device = torch.device("cuda:0")
        a = torch.arange(10, device=device, dtype=torch.float32)
        b = torch.ones(10, device=device)
        c = (a + b).sum().item()
        elapsed = (time.time() - start) * 1000
        record("cuda:op", c == 55.0, f"sum={c} ms={elapsed:.1f}")
        # Also capture device name (cheap call)
        try:
            name = torch.cuda.get_device_name(0)
            record("cuda:device", True, name)
        except Exception as e:  # pragma: no cover
            record("cuda:device", False, repr(e))
    except Exception as e:
        record("cuda:op", False, repr(e))

def ndscan_basic():
    try:
        nd = importlib.import_module("ndscan")
        ok = hasattr(nd, "__version__") or hasattr(nd, "scan")
        record("ndscan:attr", ok, "has version or scan")
    except Exception as e:
        record("ndscan:attr", False, repr(e))

def qasync_event_loop():
    # Use offscreen platform to avoid real display requirement.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import asyncio
        import qasync  # type: ignore
        from PyQt6.QtWidgets import QApplication
        # Avoid creating multiple QApplication instances.
        app = QApplication.instance() or QApplication([])
        async def tiny():
            await asyncio.sleep(0.01)
            return 42
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        with loop:
            val = loop.run_until_complete(tiny())
        record("qasync:eventloop", val == 42, f"result={val}")
    except Exception as e:
        record("qasync:eventloop", False, repr(e))

def env_checks():
    ve = os.environ.get("VIRTUAL_ENV", "")
    record("env:VIRTUAL_ENV", bool(ve), ve or "missing")
    pyp = os.environ.get("PYTHONPATH", "")
    excessive = len(pyp.split(":")) > 25
    record("env:PYTHONPATH", not excessive, f"segments={len(pyp.split(':'))}")
    qt_plugin = os.environ.get("QT_PLUGIN_PATH")
    if qt_plugin:
        qt_parts = [p for p in qt_plugin.split(":") if p]
        qt_missing = [p for p in qt_parts if not os.path.isdir(p)]
        qt_ok = len(qt_missing) == 0 and len(qt_parts) > 0
        qt_detail = f"dirs={len(qt_parts)} missing={len(qt_missing)}" + ("" if not qt_missing else " first_missing=" + qt_missing[0])
        record("env:QT_PLUGIN_PATH", qt_ok, qt_detail)
    qml_import = os.environ.get("QML2_IMPORT_PATH")
    if qml_import:
        qml_parts = [p for p in qml_import.split(":") if p]
        existing = [p for p in qml_parts if os.path.isdir(p)]
        missing = [p for p in qml_parts if not os.path.isdir(p)]
        qml_ok = len(existing) > 0
        detail = f"existing={len(existing)} missing={len(missing)}" + ("" if not missing else " first_missing=" + missing[0])
        record("env:QML2_IMPORT_PATH", qml_ok, detail)

def artiq_cli():
    import subprocess, shlex
    try:
        out = subprocess.run(["which", "artiq_master"], capture_output=True, text=True)
        path = out.stdout.strip()
        ok = out.returncode == 0 and os.path.isfile(path)
        record("cli:artiq_master", ok, path or out.stderr.strip())
        vout = subprocess.run(["artiq_master", "--version"], capture_output=True, text=True, timeout=5)
        record("cli:artiq_version", vout.returncode == 0, vout.stdout.strip().splitlines()[0] if vout.stdout else vout.stderr.strip())
    except Exception as e:
        record("cli:artiq_master", False, repr(e))

def wrappers_check():
    for w in ["uv-add", "uv-remove"]:
        p = shutil.which(w)
        record(f"cli:{w}", bool(p), p or "missing")

def uv_lock_hashes():
    # Ensure no download.pytorch.org wheel entries missing hash
    lock = os.path.join(os.getcwd(), "uv.lock")
    if not os.path.isfile(lock):
        record("lock:present", False, "uv.lock missing")
        return
    import re
    missing = 0
    with open(lock, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "https://download.pytorch.org/" in line and ".whl" in line:
                if "hash" not in line:
                    missing += 1
    record("lock:pytorch_hashes", missing == 0, f"missing={missing}")

def opengl_check():
    # Attempt to dlopen libGL (optional diagnostic)
    try:
        import ctypes
        ctypes.CDLL("libGL.so.1")
        record("opengl:libGL", True, "loaded")
    except OSError as e:
        record("opengl:libGL", False, str(e))
    except Exception as e:  # pragma: no cover
        record("opengl:libGL", False, repr(e))

import shutil  # placed after function definitions to avoid reordering above

def summarize():
    width = max(len(n) for n,_,_ in RESULTS) + 2
    print("Smoke Test Results:\n")
    failures = 0
    for name, ok, detail in RESULTS:
        status = "OK" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  {name.ljust(width)} {status:4s}  {detail}")
    print("")
    if failures:
        print(f"❌ {failures} check(s) failed.")
        sys.exit(1)
    else:
        print("✅ All checks passed.")

def main():
    import_and_version()
    cuda_test()
    ndscan_basic()
    qasync_event_loop()
    env_checks()
    artiq_cli()
    wrappers_check()
    uv_lock_hashes()
    opengl_check()
    summarize()

if __name__ == "__main__":
    main()