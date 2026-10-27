"""Turns raw review text into customer insights: per-aspect sentiment (vector search + lexicon),
then an LLM-written summary when available."""
import json
import re

from . import catalog, db, llm, vectorstore
from .connectors import youtube

ASPECTS = {
    "sound": "sound quality bass treble clarity detail audio",
    "comfort": "comfort comfortable fit weight ears pressure long wear",
    "battery": "battery life charging hours lasts",
    "noise cancelling": "noise cancelling ANC quiet commute plane noise",
    "calls": "microphone call quality voice meetings",
    "value": "value price worth money cheap expensive",
    "durability": "build quality durable broke hinge case materials",
}
_POS = set("great excellent amazing love loved comfortable clear crisp best perfect solid good impressive "
           "worth comfy superb fantastic smooth reliable punchy warm detailed quiet".split())
_NEG = set("bad poor worst hate hated uncomfortable muddy tinny broke broken cheap disappointing issue "
           "problem problems annoying weak flimsy pain painful lacking harsh fiddly bulky".split())


def sentiment(text):
    w = re.findall(r"[a-z']+", text.lower())
    p, n = sum(x in _POS for x in w), sum(x in _NEG for x in w)
    return (p - n) / (p + n) if p + n else 0.0


def demo_reviews(p):
    """Clearly-labelled synthetic placeholders so the app runs without API keys. NOT real customer data."""
    rows = [f"{p['name']}: {t}. (demo placeholder)" for t in p["pros"]]
    rows += [f"{p['name']}: a common complaint is {t}. (demo placeholder)" for t in p["cons"]]
    return [{"text": t, "url": "", "source": "demo"} for t in rows]


def ingest():
    """Pull fresh reviews for every product (YouTube if keyed, demo otherwise) into the vector store."""
    added = 0
    for p in catalog.all_products():
        try:
            fresh = [dict(r, source="youtube") for r in youtube.fetch(p["name"])]
        except Exception as e:
            print("YouTube fetch failed for", p["slug"], e)
            fresh = []
        if not fresh and not db.one("SELECT 1 FROM reviews WHERE slug=?", (p["slug"],)):
            fresh = demo_reviews(p)
        for r in fresh:
            r.update(slug=p["slug"], sentiment=sentiment(r["text"]))
        added += vectorstore.add_reviews(fresh)
    return added


def build(slug):
    p = catalog.get(slug)
    n = db.one("SELECT COUNT(*) c, AVG(sentiment) s FROM reviews WHERE slug=?", (slug,))
    real = db.one("SELECT COUNT(*) c FROM reviews WHERE slug=? AND source!='demo'", (slug,))["c"]
    aspects = {}
    for a, q in ASPECTS.items():
        hits = [h for h in vectorstore.search(f"{p['name']} {q}", k=5, slug=slug) if h["score"] > 0.05]
        if hits:
            aspects[a] = {"sentiment": round(sum(h["sentiment"] for h in hits) / len(hits), 2),
                          "evidence": [h["text"] for h in hits[:2]]}
    summary = None
    if real:
        sample = [h["text"] for h in vectorstore.search(f"{p['name']} overall opinion", k=12, slug=slug)]
        summary = llm.complete(
            "You summarise customer feedback for a headphone buying guide. Be balanced and factual; use only the "
            "comments given; never invent specs, prices or quotes.",
            f"Product: {p['name']}\nComments:\n- " + "\n- ".join(sample) +
            "\n\nWrite 3 short sentences: who it suits, what people praise, what people criticise.", 300)
    data = {"n": n["c"], "real_n": real, "avg": round(n["s"] or 0, 2), "aspects": aspects,
            "summary": summary, "demo": real == 0}
    db.x("INSERT OR REPLACE INTO insights VALUES(?,?,?)", (slug, json.dumps(data), db.now()))
    return data


def get(slug):
    r = db.one("SELECT data FROM insights WHERE slug=?", (slug,))
    return json.loads(r["data"]) if r else None
