"""Check that a Hugging Face Space can reach the course endpoints, before deploying the app.

    hf auth login                                     # once, with a write token
    uv run --with huggingface_hub python deploy/huggingface/probe_space.py --space <user>/declareright-probe

Creates a small public Docker Space from deploy/huggingface/probe/, waits for it to run, asks it to
open TCP connections to the chat (1033) and embeddings (1035) ports, prints the result, then
deletes the Space (--keep to keep it). No keys or certificates are uploaded.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

from huggingface_hub import HfApi

HERE = Path(__file__).resolve().parent


def space_url(repo_id: str) -> str:
    owner, name = repo_id.split("/")
    sub = f"{owner}-{name}".lower().replace("_", "-").replace(".", "-")
    return f"https://{sub}.hf.space/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="<user>/<space name>")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    api = HfApi()
    api.create_repo(a.space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(repo_id=a.space, repo_type="space", folder_path=HERE / "probe")
    print(f"uploaded; building https://huggingface.co/spaces/{a.space}", flush=True)
    stage = None
    for _ in range(90):  # up to ~15 minutes
        stage = api.get_space_runtime(a.space).stage
        if stage == "RUNNING":
            break
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"):
            raise SystemExit(f"Space failed: {stage} (see its logs on the Space page)")
        print(f"  {stage} ...", flush=True)
        time.sleep(10)
    if stage != "RUNNING":
        raise SystemExit(f"Space not running after 15 minutes: {stage}")
    url = space_url(a.space)
    result = None
    for _ in range(12):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                result = json.loads(r.read())
                break
        except Exception as e:  # noqa: BLE001 - the app may still be starting
            print(f"  waiting for the app ({type(e).__name__}) ...", flush=True)
            time.sleep(10)
    print(json.dumps(result, indent=1))
    if result:
        ok = all(v.get("ok") for k, v in result.items() if "endpoint" in k)
        print("\nRESULT:", "the Space reaches both endpoints" if ok else "BLOCKED: a Space cannot reach the endpoints")
    if not a.keep:
        api.delete_repo(a.space, repo_type="space")
        print(f"deleted {a.space}")


if __name__ == "__main__":
    main()
