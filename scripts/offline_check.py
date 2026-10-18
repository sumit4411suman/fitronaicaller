"""Offline verification. Run with the PC's network DISABLED after models are installed.

    python scripts/offline_check.py

Checks: backend health, contact CRUD round-trip, knowledge retrieval, local LLM reply (if Ollama is running),
Piper TTS and faster-whisper loopback (if voices/models are present). Prints a table; nothing is assumed.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

import httpx

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ("services/local-backend", "packages/shared-protocol")]
from sellagent_backend.config import get_settings  # noqa: E402
from sellagent_backend.security.secret_store import read_secret_file  # noqa: E402


def internet_reachable() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=2).close()
        return True
    except OSError:
        return False


def main() -> int:
    s = get_settings()
    token = read_secret_file(s.local_token_path)
    if not token:
        print("backend has never run (no local token). Start SELL AGENT first.")
        return 2
    c = httpx.Client(base_url=f"http://{s.host}:{s.port}", headers={"Authorization": f"Bearer {token}"}, timeout=120)
    rows: list[tuple[str, str, str]] = []
    rows.append(("internet", "OFFLINE (good)" if not internet_reachable() else "ONLINE - disconnect to prove offline operation", ""))
    try:
        h = c.get("/api/v1/health").json()
        rows.append(("backend health", "ok" if h["ok"] else "FAIL", f"rev {h['database']['revision']}"))
    except Exception as exc:  # noqa: BLE001
        rows.append(("backend health", "FAIL", str(exc)))
        _print(rows)
        return 1
    t0 = time.perf_counter()
    r = c.post("/api/v1/contacts", json={"business_name": f"Offline Check {int(t0)}", "phone": "9876500000"}, params={"allow_duplicate": True})
    ok = r.status_code == 201
    if ok:
        c.delete(f"/api/v1/contacts/{r.json()['id']}", params={"hard": True})
    rows.append(("CRM write/read/delete", "ok" if ok else f"FAIL {r.status_code}", f"{(time.perf_counter() - t0) * 1000:.0f} ms"))
    hits = c.get("/api/v1/knowledge/retrieve", params={"q": "price per month"}).json()
    rows.append(("knowledge retrieval (FTS5)", "ok" if hits else "FAIL", hits[0]["ref"] if hits else ""))
    ai = c.get("/api/v1/ai/status").json()
    if ai["available"] and ai["configured_model_installed"]:
        t = c.post("/api/v1/ai/chat-test", json={"prompt": "Say hello in one short sentence.", "language": "en", "max_tokens": 32})
        if t.status_code == 200:
            j = t.json()
            rows.append(("local LLM", "ok", f"first token {j['first_token_ms']:.0f} ms, {j['tokens_per_second'] or 0:.1f} tok/s, model {ai['configured_model']}"))
            t2 = c.post("/api/v1/ai/chat-test", json={"prompt": "एक छोटे वाक्य में नमस्ते कहिए।", "language": "hi", "max_tokens": 32}).json()
            rows.append(("local LLM Hindi", "ok" if t2.get("detected_language") in ("hi", "mixed") else "language mismatch", t2.get("text", "")[:60]))
        else:
            rows.append(("local LLM", "FAIL", t.text[:120]))
    else:
        rows.append(("local LLM", "NOT AVAILABLE", ai["message"]))
    sp = c.get("/api/v1/speech/status").json()
    for lang in ("en", "hi"):
        if sp["tts"]["available"] and sp["stt"]["available"] and sp["tts"][f"voice_{lang}"]:
            lb = c.post("/api/v1/speech/loopback", params={"language": lang})
            if lb.status_code == 200:
                res = lb.json()["results"]
                rows.append((f"speech loopback {lang} (SIMULATED)", "ok" if all(r_["error"] is None for r_ in res) else "partial", "; ".join(f"tts {r_['tts_latency_ms'] or 0:.0f}ms stt {r_['stt_latency_ms'] or 0:.0f}ms overlap {r_['word_overlap']}" for r_ in res)))
            else:
                rows.append((f"speech loopback {lang}", "FAIL", lb.text[:120]))
        else:
            rows.append((f"speech {lang}", "NOT AVAILABLE", f"stt: {sp['stt']['message']}; tts: {sp['tts']['message']}"))
    _print(rows)
    Path("docs/benchmarks").mkdir(parents=True, exist_ok=True)
    Path("docs/benchmarks/offline_check_last.json").write_text(json.dumps([{"check": a, "result": b, "detail": d} for a, b, d in rows], indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def _print(rows: list[tuple[str, str, str]]) -> None:
    w = max(len(r[0]) for r in rows)
    for name, result, detail in rows:
        print(f"{name:<{w}}  {result:<44}  {detail}")


if __name__ == "__main__":
    sys.exit(main())
