"""Benchmark local LLMs on the target machine. Run on the Windows PC:

    python -m sellagent_ai.benchmark --provider ollama --models qwen3:1.7b qwen3:4b --out docs/benchmarks/llm.json

Measures: model availability, first-token latency, tokens/s, total time, Ollama process RSS (psutil), Hindi and English
quality probes (does the reply stay in language, does it avoid inventing numbers), and JSON-format reliability.
Nothing here is pre-filled: results exist only after you run it.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sellagent_ai.guardrails import check_reply
from sellagent_ai.language import detect
from sellagent_ai.llm import ChatMessage, ProviderUnavailable, collect, make_provider

PROBES = [
    {"id": "en_price", "lang": "en", "system": "You are a FITRON sales assistant. Only state: Professional plan is ₹1,999 per month. Reply in English in one sentence.", "user": "How much does FITRON cost?", "expect_lang": "en"},
    {"id": "hi_price", "lang": "hi", "system": "आप FITRON के सेल्स सहायक हैं। केवल यह बताएं: प्रोफेशनल प्लान ₹1,999 प्रति माह है। हिंदी (देवनागरी) में एक वाक्य में उत्तर दें।", "user": "FITRON का दाम कितना है?", "expect_lang": "hi"},
    {"id": "en_unknown", "lang": "en", "system": "You are a FITRON sales assistant. You know only: FITRON is gym accounting software. If asked anything else say you do not have confirmed information. One sentence, English.", "user": "Does FITRON integrate with WhatsApp and Tally?", "expect_lang": "en"},
    {"id": "hi_unknown", "lang": "hi", "system": "आप FITRON के सेल्स सहायक हैं। आपको केवल इतना पता है: FITRON जिम अकाउंटिंग सॉफ़्टवेयर है। कुछ और पूछा जाए तो कहें कि आपके पास पुष्टि की गई जानकारी नहीं है। एक वाक्य, हिंदी।", "user": "क्या इसमें बायोमेट्रिक अटेंडेंस है?", "expect_lang": "hi"},
    {"id": "json", "lang": "en", "system": "Return only JSON with keys intent (one of: price, opt_out, callback, demo, other) and language (hi or en).", "user": "Mujhe abhi time nahi hai, baad mein call karo.", "expect_json": True},
]


def _ollama_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    total = 0.0
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            if p.info["name"] and "ollama" in p.info["name"].lower():
                total += p.info["memory_info"].rss / 1e6
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total or None


def run(provider_kind: str, models: list[str], runs: int = 3, ollama_url: str = "http://127.0.0.1:11434", llamacpp_url: str = "http://127.0.0.1:8080") -> dict:
    provider = make_provider(provider_kind, ollama_url=ollama_url, llamacpp_url=llamacpp_url)
    ok, msg = provider.available()
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(), "machine": {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0], "cpu_count": __import__("os").cpu_count()},
        "provider": provider_kind, "provider_available": ok, "provider_message": msg, "models": {},
    }
    if not ok:
        return report
    for model in models:
        entry: dict = {"probes": {}, "errors": []}
        # cold load
        t0 = time.perf_counter()
        try:
            collect(provider, [ChatMessage("user", "hi")], model=model, max_tokens=4, timeout=600)
            entry["cold_load_ms"] = (time.perf_counter() - t0) * 1000
        except ProviderUnavailable as exc:
            entry["errors"].append(f"load: {exc}")
            report["models"][model] = entry
            continue
        entry["rss_mb_after_load"] = _ollama_rss_mb()
        for probe in PROBES:
            ft, tps, tot, texts = [], [], [], []
            for _ in range(runs):
                try:
                    r = collect(provider, [ChatMessage("system", probe["system"]), ChatMessage("user", probe["user"])], model=model, max_tokens=96, timeout=120)
                except ProviderUnavailable as exc:
                    entry["errors"].append(f"{probe['id']}: {exc}")
                    break
                if r.first_token_ms is not None:
                    ft.append(r.first_token_ms)
                if r.tokens_per_second:
                    tps.append(r.tokens_per_second)
                tot.append(r.total_ms)
                texts.append(r.text)
            if not texts:
                continue
            quality: dict = {}
            if probe.get("expect_lang"):
                quality["language_match_rate"] = sum(1 for t in texts if detect(t) in (probe["expect_lang"], "mixed")) / len(texts)
            if probe.get("expect_json"):
                def _is_json(t: str) -> bool:
                    try:
                        json.loads(t.strip().strip("`").removeprefix("json").strip())
                        return True
                    except Exception:  # noqa: BLE001
                        return False
                quality["json_valid_rate"] = sum(1 for t in texts if _is_json(t)) / len(texts)
            facts = [{"price_inr": 1999}] if "price" in probe["id"] else [{}]
            quality["guardrail_pass_rate"] = sum(1 for t in texts if check_reply(t, approved_facts=facts, state="product_explanation").allowed) / len(texts)
            entry["probes"][probe["id"]] = {
                "first_token_ms_median": statistics.median(ft) if ft else None, "tokens_per_second_median": statistics.median(tps) if tps else None,
                "total_ms_median": statistics.median(tot), "samples": texts, "quality": quality,
            }
        entry["rss_mb_peak_seen"] = _ollama_rss_mb()
        report["models"][model] = entry
    return report


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark local LLMs for SELL AGENT")
    ap.add_argument("--provider", default="ollama", choices=["ollama", "llamacpp"])
    ap.add_argument("--models", nargs="+", default=["qwen3:1.7b", "qwen3:4b"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    rep = run(a.provider, a.models, a.runs)
    text = json.dumps(rep, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(text)
    return 0 if rep["provider_available"] else 2


if __name__ == "__main__":
    sys.exit(cli())
