"""Thin Claude wrapper. Returns None when no key is set so callers can fall back to templates."""
import json
import re

from .config import settings

_client = None


def available():
    return bool(settings.anthropic_key)


def complete(system, prompt, max_tokens=1500):
    global _client
    if not available():
        return None
    try:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(api_key=settings.anthropic_key)
        r = _client.messages.create(model=settings.model, max_tokens=max_tokens, system=system,
                                    messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in r.content if b.type == "text").strip()
    except Exception as e:  # network/auth errors must never break the pipeline
        print("LLM error:", e)
        return None


def complete_json(system, prompt, max_tokens=1500):
    out = complete(system + "\nReply with a single valid JSON value and nothing else.", prompt, max_tokens)
    if not out:
        return None
    m = re.search(r"[\[{].*[\]}]", out, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None
