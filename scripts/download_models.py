"""Explicit, user-acknowledged model downloads for SELL AGENT.

Nothing is downloaded unless you pass --yes. Every item prints its size, licence and destination first.
Run on the Windows PC (needs internet for this step only):

    python scripts/download_models.py --list
    python scripts/download_models.py --llm qwen3:1.7b --whisper small --piper en_US-lessac-medium hi_IN-pratham-medium --yes

After this step, set privacy.allow_external_network back to false (it is false by default) and run
scripts/offline_check.py with the network disconnected.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

CATALOG = {
    "llm": {
        "qwen3:1.7b": {"approx_gb": 1.4, "license": "Apache-2.0", "via": "ollama pull", "notes": "default candidate; CPU friendly"},
        "qwen3:4b": {"approx_gb": 2.6, "license": "Apache-2.0", "via": "ollama pull", "notes": "3B-class alternative (Qwen2.5-3B excluded: non-commercial research licence)"},
    },
    "whisper": {
        "tiny": {"approx_mb": 75, "repo": "Systran/faster-whisper-tiny", "license": "MIT (OpenAI Whisper weights)"},
        "base": {"approx_mb": 145, "repo": "Systran/faster-whisper-base", "license": "MIT"},
        "small": {"approx_mb": 480, "repo": "Systran/faster-whisper-small", "license": "MIT", "notes": "recommended starting point for Hindi+English on CPU"},
        "medium": {"approx_mb": 1500, "repo": "Systran/faster-whisper-medium", "license": "MIT", "notes": "better Hindi accuracy, ~2-3x slower"},
    },
    "piper": {
        # Voice files live under rhasspy/piper-voices on Hugging Face: <lang>/<locale>/<name>/<quality>/<file>
        "en_US-lessac-medium": {"approx_mb": 63, "path": "en/en_US/lessac/medium/en_US-lessac-medium", "license": "see MODEL_CARD in the voice folder (most Piper voices: CC-BY/MIT/public domain datasets)"},
        "en_GB-alan-medium": {"approx_mb": 63, "path": "en/en_GB/alan/medium/en_GB-alan-medium", "license": "see MODEL_CARD"},
        # Hindi: verify availability at https://huggingface.co/rhasspy/piper-voices/tree/main/hi before relying on it.
        "hi_IN-pratham-medium": {"approx_mb": 63, "path": "hi/hi_IN/pratham/medium/hi_IN-pratham-medium", "license": "see MODEL_CARD (verify before commercial use)", "notes": "listed in rhasspy/piper-voices VOICES.md; size unverified"},
        "hi_IN-priyamvada-medium": {"approx_mb": 63, "path": "hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium", "license": "see MODEL_CARD (verify before commercial use)", "notes": "listed in rhasspy/piper-voices VOICES.md; size unverified"},
    },
}
HF = "https://huggingface.co"


def models_dir() -> Path:
    sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ("services/local-backend", "packages/shared-protocol")]
    from sellagent_backend.config import get_settings

    s = get_settings()
    s.ensure_dirs()
    return s.models_dir


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310 - fixed https hosts only
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--llm", nargs="*", default=[])
    ap.add_argument("--whisper", nargs="*", default=[])
    ap.add_argument("--piper", nargs="*", default=[])
    ap.add_argument("--yes", action="store_true", help="acknowledge the downloads listed above")
    a = ap.parse_args()
    if a.list or not (a.llm or a.whisper or a.piper):
        print(json.dumps(CATALOG, indent=2))
        return 0
    plan = [("llm", m, CATALOG["llm"].get(m)) for m in a.llm] + [("whisper", m, CATALOG["whisper"].get(m)) for m in a.whisper] + [("piper", m, CATALOG["piper"].get(m)) for m in a.piper]
    for kind, name, meta in plan:
        if meta is None:
            print(f"unknown {kind} model {name!r}; see --list", file=sys.stderr)
            return 2
        size = meta.get("approx_gb") and f"~{meta['approx_gb']} GB" or f"~{meta.get('approx_mb')} MB"
        print(f"{kind:8} {name:28} {size:>9}  licence: {meta['license']}  {meta.get('notes', '')}")
    free = shutil.disk_usage(Path.home()).free / 1e9
    print(f"free disk: {free:.1f} GB")
    if not a.yes:
        print("\nRe-run with --yes to download the items above.")
        return 1
    mdir = models_dir()
    for kind, name, meta in plan:
        if kind == "llm":
            if shutil.which("ollama") is None:
                print("ollama is not installed or not on PATH (https://ollama.com/download/windows)", file=sys.stderr)
                return 3
            subprocess.run(["ollama", "pull", name], check=True)  # noqa: S603,S607
        elif kind == "whisper":
            try:
                from faster_whisper import download_model
            except ImportError:
                print("pip install -r requirements-speech.txt first", file=sys.stderr)
                return 3
            out = download_model(name, output_dir=str(mdir / f"faster-whisper-{name}"))
            print(f"  whisper {name} -> {out}")
        else:
            base = f"{HF}/rhasspy/piper-voices/resolve/main/{meta['path']}"
            for suffix in (".onnx", ".onnx.json"):
                _download(base + suffix, mdir / "piper" / f"{name}{suffix}")
            try:
                _download(f"{HF}/rhasspy/piper-voices/resolve/main/{Path(meta['path']).parent}/MODEL_CARD", mdir / "piper" / f"{name}.MODEL_CARD")
            except Exception as exc:  # noqa: BLE001
                print(f"  (model card not fetched: {exc})")
    print(f"\nDone. Models directory: {mdir}\nNow set ai.* settings in the app and run scripts/offline_check.py with the network OFF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
