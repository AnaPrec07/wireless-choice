"""Hybrid recommender: vector similarity of the shopper's need against review evidence,
filtered by hard constraints, boosted by sentiment and Google Trends momentum."""
from . import catalog, insights, llm, vectorstore
from .connectors import trends


def parse_constraints(text):
    t = text.lower()
    c = {}
    if any(w in t for w in ("run", "gym", "cycl", "bike", "sport", "workout")):
        c["activity"] = True
    if any(w in t for w in ("budget", "cheap", "affordable", "under")):
        c["tier"] = "budget"
    elif any(w in t for w in ("premium", "best", "top of the line", "no compromise")):
        c["tier"] = "premium"
    if "earbud" in t or "in-ear" in t:
        c["form"] = "in-ear"
    elif "over-ear" in t or "over ear" in t:
        c["form"] = "over-ear"
    elif "open" in t or "bone" in t:
        c["form"] = "open-ear"
    return c


def recommend(need, form=None, tier=None, anc=None, k=3):
    c = parse_constraints(need)
    form, tier = form or c.get("form"), tier or c.get("tier")
    tr = trends.latest()
    hits = vectorstore.search(need, k=60)
    ev = {}
    for h in hits:
        ev.setdefault(h["slug"], []).append(h)
    ranked = []
    for p in catalog.all_products():
        if form and p["form"] != form:
            continue
        if tier and p["tier"] != tier:
            continue
        if anc is not None and bool(p["anc"]) != bool(anc):
            continue
        hs = ev.get(p["slug"], [])
        rel = sum(h["score"] for h in hs[:3]) / 3
        sent = sum(h["sentiment"] for h in hs[:3]) / max(len(hs[:3]), 1)
        boost = (tr.get(p["slug"], 50) - 50) / 500          # trends nudge, small by design
        score = rel + 0.15 * sent + boost
        if c.get("activity") and p["form"] == "open-ear":
            score += 0.15
        ranked.append((score, p, hs[:2]))
    ranked.sort(key=lambda x: -x[0])
    top = [{"product": p, "score": round(s, 3), "evidence": [h["text"] for h in hs],
            "insights": insights.get(p["slug"]), "link": catalog.go_url(p["slug"], "rec")}
           for s, p, hs in ranked[:k]]
    if top:
        why = llm.complete(
            "You are a candid headphone advisor. Use ONLY the facts given. No prices, no invented specs. "
            "Max 90 words per product, as a markdown bullet list.",
            f"Shopper need: {need}\n" + "\n".join(
                f"- {t['product']['name']}: {t['product']['blurb']} Pros: {t['product']['pros']} Cons: {t['product']['cons']} "
                f"Customer evidence: {t['evidence']}" for t in top) + "\nExplain why each fits (and one caveat).", 500)
        if why:
            top[0]["why_all"] = why
    return top
