"""Regenerate webui/model_catalog.json from openrouter.ai.

Run this by hand when the shipped model list changes. The app never calls it:
the catalog is baked in so a run needs no network, which is the point of the
product. Usage:  python3 tools/refresh_catalog.py
"""
import json
import os
import re
import urllib.request

# ollama tag -> (openrouter model id, ollama library slug)
MAP = {
    "llama3.1:8b": ("meta-llama/llama-3.1-8b-instruct", "llama3.1"),
    "llama3.2:3b": ("meta-llama/llama-3.2-3b-instruct", "llama3.2"),
    "llama3.2:1b": ("meta-llama/llama-3.2-1b-instruct", "llama3.2"),
    "qwen3:8b": ("qwen/qwen3-8b", "qwen3"),
    "gemma3:4b": ("google/gemma-3-4b-it", "gemma3"),
    "phi4-mini:3.8b": ("microsoft/phi-4", "phi4-mini"),
}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "webui", "model_catalog.json")


def brief(text, limit=180):
    text = re.sub(r"\s+", " ", (text or "").strip())
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:stop + 1] if stop > 80 else cut.rsplit(" ", 1)[0] + "…").strip()


def main():
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30) as r:
        data = {m["id"]: m for m in json.load(r)["data"]}
    out = {}
    for tag, (oid, slug) in MAP.items():
        m = data.get(oid)
        if not m:
            print("  missing on openrouter:", oid)
            continue
        out[tag] = {
            "title": m["name"].split(": ", 1)[-1],
            "vendor": m["name"].split(": ", 1)[0] if ": " in m["name"] else "",
            "description": brief(m.get("description")),
            "context": m.get("context_length"),
            "pull": f"ollama pull {tag}",
            "url": f"https://ollama.com/library/{slug}",
            "source": oid,
        }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"_note": "Generated from openrouter.ai/api/v1/models. Shipped so the "
                            "UI never has to reach the network at runtime.",
                   "models": out}, f, indent=1, ensure_ascii=False)
    print(f"wrote {os.path.normpath(OUT)} with {len(out)} models")


if __name__ == "__main__":
    main()
