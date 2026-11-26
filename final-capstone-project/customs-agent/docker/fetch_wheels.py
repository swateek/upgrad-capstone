"""Download the Linux packages for the Docker image on this machine, so the build never fetches
from PyPI (SETUP.md step 13).

    uv run python docker/fetch_wheels.py            # for this Mac's chip (arm64 -> linux/aarch64)
    uv run python docker/fetch_wheels.py --arch x86_64

Why: from inside Docker Desktop, PyPI downloaded at ~28 KB/s on the owner's Mac while the Mac
itself reached it in 0.06 s; the ~150 MB of packages would have taken over an hour. The Mac
downloads them in seconds and the build installs them offline (`--no-index`).

Writes docker/wheels/ (git-ignored): one wheel per package at its uv.lock version, for Linux,
CPython 3.12, plus requirements.txt. PyTorch is the CPU-only build from PyTorch's own index; the
PyPI build pulls ~20 NVIDIA CUDA packages (several GB) a container without an NVIDIA GPU cannot
use, so those are left out. Environment markers are evaluated for Linux, not for this Mac.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from packaging.markers import Marker

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docker" / "wheels"
SKIP = ("nvidia-", "cuda-", "triton==", "torch==")
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def linux_env(arch: str) -> dict[str, str]:
    """The marker environment of the image: python:3.12-slim on Linux."""
    return {
        "implementation_name": "cpython",
        "implementation_version": "3.12.0",
        "os_name": "posix",
        "platform_machine": arch,
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Linux",
        "platform_version": "",
        "python_full_version": "3.12.0",
        "python_version": "3.12",
        "sys_platform": "linux",
    }


def locked_pins(arch: str) -> tuple[list[str], str]:
    """uv.lock as name==version pins for the image (markers applied), and the torch version."""
    text = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    env, pins, torch = linux_env(arch), [], None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        req, _, marker = line.partition(";")
        req = req.strip()
        if marker.strip() and not Marker(marker.strip()).evaluate(env):
            continue
        if req.startswith("torch=="):
            torch = req.split("==", 1)[1]
        if req.startswith(SKIP):
            continue
        pins.append(req)
    if torch is None:
        sys.exit("torch is not in uv.lock")
    return pins, torch


def download(reqs: list[str], arch: str, *, index: str | None = None) -> None:
    cmd = [
        "uvx",
        "pip",
        "download",
        "--quiet",
        "--no-deps",
        "--dest",
        str(OUT),
        "--only-binary=:all:",
        "--implementation",
        "cp",
        "--python-version",
        "312",
        "--abi",
        "cp312",
        "--abi",
        "abi3",
        "--abi",
        "none",
    ]
    for tag in ("manylinux_2_28", "manylinux_2_17", "manylinux2014"):
        cmd += ["--platform", f"{tag}_{arch}"]
    if index:
        cmd += ["--index-url", index]
    subprocess.run(cmd + reqs, check=True)


def main() -> int:
    host = {
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "x86_64": "x86_64",
        "AMD64": "x86_64",
    }
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--arch",
        default=host.get(platform.machine(), "x86_64"),
        choices=("aarch64", "x86_64"),
        help="CPU of the Docker image",
    )
    args = ap.parse_args()

    pins, torch = locked_pins(args.arch)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    download([f"torch=={torch}"], args.arch, index=TORCH_CPU_INDEX)
    download(pins, args.arch)
    # pin torch without a local version tag: "2.15.0" also matches the x86 "2.15.0+cpu" wheel
    (OUT / "requirements.txt").write_text("\n".join([f"torch=={torch}", *pins]) + "\n")
    n = len(list(OUT.glob("*.whl")))
    print(
        f"{n} wheels for linux/{args.arch} in {OUT.relative_to(ROOT)} ({len(pins) + 1} pins)"
    )
    if n != len(pins) + 1:
        print(
            "warning: the number of wheels does not match the pins; check the output above"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
