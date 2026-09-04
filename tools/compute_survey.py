"""Survey all compute available on this machine before local model development.

CLAUDE.md Gate 2: run this (and record the output in Claude_log.md) before
starting any local training/experimentation, so the work actually uses the
hardware that exists — on Tile_Sorting, CPU-only torch silently ignored the
machine's NVIDIA GPU until this check was done; installing CUDA torch gave a
15-20x training speedup.

Usage:
    python tools/compute_survey.py                # human-readable report
    python tools/compute_survey.py --json out.json  # also save as JSON

Standard library only; uses torch and nvidia-smi opportunistically if present.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _read_linux_cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def survey_cpu() -> dict:
    info = {
        "model": None,
        "logical_cores": os.cpu_count(),
        "machine": platform.machine(),
    }
    if platform.system() == "Linux":
        info["model"] = _read_linux_cpu_model()
    if not info["model"]:
        info["model"] = platform.processor() or None
    return info


def survey_ram() -> dict:
    system = platform.system()
    total = available = None
    try:
        if system == "Linux":
            meminfo = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, _, rest = line.partition(":")
                meminfo[key.strip()] = rest.strip()
            total = int(meminfo["MemTotal"].split()[0]) * 1024
            available = int(meminfo["MemAvailable"].split()[0]) * 1024
        elif system == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total, available = stat.ullTotalPhys, stat.ullAvailPhys
        elif system == "Darwin":
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, AttributeError):
        pass
    return {"total_bytes": total, "available_bytes": available}


def survey_disk() -> dict:
    usage = shutil.disk_usage(Path.cwd())
    return {"path": str(Path.cwd()), "total_bytes": usage.total, "free_bytes": usage.free}


def survey_nvidia_smi() -> list[dict]:
    """GPU info straight from the driver — works even when torch is CPU-only."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5:
            gpus.append(
                {
                    "name": parts[0],
                    "vram_total_mb": _to_int(parts[1]),
                    "vram_free_mb": _to_int(parts[2]),
                    "driver_version": parts[3],
                    "compute_capability": parts[4],
                }
            )
    return gpus


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def survey_torch() -> dict:
    """What the installed ML framework can actually see and use."""
    info = {"installed": False}
    try:
        import torch  # noqa: PLC0415 — optional dependency, probed at runtime
    except ImportError:
        return info

    info["installed"] = True
    info["version"] = torch.__version__
    info["cuda_built"] = torch.backends.cuda.is_built()
    info["cuda_available"] = torch.cuda.is_available()
    if info["cuda_available"]:
        info["devices"] = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            info["devices"].append(
                {"index": i, "name": props.name, "vram_total_mb": props.total_memory // (1024 * 1024)}
            )
    mps = getattr(getattr(torch.backends, "mps", None), "is_available", lambda: False)
    info["mps_available"] = bool(mps())
    return info


def build_report() -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version.split()[0],
        },
        "cpu": survey_cpu(),
        "ram": survey_ram(),
        "disk": survey_disk(),
        "nvidia_gpus": survey_nvidia_smi(),
        "torch": survey_torch(),
    }


def _gb(n: int | None) -> str:
    return f"{n / (1024 ** 3):.1f} GB" if n is not None else "unknown"


def summarize_actions(report: dict) -> list[str]:
    """The point of the survey: what to DO about what was found."""
    actions = []
    torch_info = report["torch"]
    has_nvidia = bool(report["nvidia_gpus"])

    if has_nvidia and torch_info.get("installed") and not torch_info.get("cuda_available"):
        actions.append(
            "An NVIDIA GPU is present but torch cannot use it (CPU-only build or "
            "driver mismatch). Install CUDA torch before training — expect a "
            "~15-20x speedup on small-model fine-tuning:\n"
            "    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
        )
    if has_nvidia and not torch_info.get("installed"):
        actions.append("NVIDIA GPU present, torch not installed yet — install the CUDA build, not the default CPU wheel.")
    if not has_nvidia and not torch_info.get("mps_available"):
        actions.append(
            "No GPU acceleration found — training runs on CPU. Prefer small "
            "backbones, keep experiment counts realistic, or train on a machine/"
            "cloud service with a GPU."
        )
    if torch_info.get("cuda_available"):
        actions.append("CUDA is working — enable it explicitly (device='cuda', fp16/amp where supported).")
        for dev in torch_info.get("devices", []):
            if dev["vram_total_mb"] and dev["vram_total_mb"] < 8192:
                actions.append(
                    f"{dev['name']} has {dev['vram_total_mb']} MB VRAM — size batch/model accordingly "
                    "(reduce batch size before reducing input resolution)."
                )
    free = report["disk"]["free_bytes"]
    if free is not None and free < 20 * 1024**3:
        actions.append(f"Only {_gb(free)} free disk here — check space before dataset copies and training runs/.")
    return actions


def print_report(report: dict) -> None:
    print("=" * 62)
    print("COMPUTE SURVEY", report["generated_at"])
    print("=" * 62)
    print(f"OS      : {report['os']['system']} {report['os']['release']}  (Python {report['os']['python']})")
    cpu = report["cpu"]
    print(f"CPU     : {cpu['model'] or 'unknown'}  [{cpu['machine']}], {cpu['logical_cores']} logical cores")
    ram = report["ram"]
    print(f"RAM     : {_gb(ram['total_bytes'])} total, {_gb(ram['available_bytes'])} available")
    disk = report["disk"]
    print(f"Disk    : {_gb(disk['free_bytes'])} free of {_gb(disk['total_bytes'])}  at {disk['path']}")

    if report["nvidia_gpus"]:
        for gpu in report["nvidia_gpus"]:
            print(
                f"GPU     : {gpu['name']} — {gpu['vram_total_mb']} MB VRAM "
                f"({gpu['vram_free_mb']} MB free), driver {gpu['driver_version']}, "
                f"compute cap {gpu['compute_capability']}"
            )
    else:
        print("GPU     : no NVIDIA GPU visible via nvidia-smi")

    t = report["torch"]
    if not t["installed"]:
        print("torch   : not installed")
    else:
        cuda = "CUDA available" if t["cuda_available"] else ("CUDA built but unavailable" if t["cuda_built"] else "CPU-only build")
        print(f"torch   : {t['version']} — {cuda}" + (", MPS available" if t.get("mps_available") else ""))
        for dev in t.get("devices", []):
            print(f"          cuda:{dev['index']} {dev['name']} ({dev['vram_total_mb']} MB)")

    actions = summarize_actions(report)
    if actions:
        print("-" * 62)
        print("ACTIONS:")
        for action in actions:
            print(f"  * {action}")
    print("=" * 62)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="Also write the report as JSON to this path")
    args = parser.parse_args()

    report = build_report()
    report["actions"] = summarize_actions(report)
    print_report(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2))
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
