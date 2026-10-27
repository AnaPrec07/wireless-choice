"""Google Trends via pytrends (unofficial). Returns {} on any failure; callers treat trends as optional."""
from .. import db, catalog
from ..config import settings


def refresh():
    if not settings.enable_trends:
        return {}
    try:
        from pytrends.request import TrendReq
        py = TrendReq(hl="en-US", tz=0, timeout=(5, 20))
        prods = catalog.all_products()
        out = {}
        for i in range(0, len(prods), 4):  # pytrends compares max 5 terms; keep 1 anchor term
            batch = prods[i:i + 4]
            terms = ["headphones"] + [p["name"] for p in batch]
            py.build_payload(terms, timeframe="today 3-m")
            df = py.interest_over_time()
            if df.empty:
                continue
            for p in batch:
                s = df[p["name"]]
                # recent momentum: mean of last 4 weeks vs. mean of the period
                out[p["slug"]] = float(s.tail(4).mean() / (s.mean() or 1)) * 50
        with db.tx() as c:
            for slug, v in out.items():
                c.execute("INSERT INTO trends VALUES(?,?,?)", (slug, v, db.now()))
        return out
    except Exception as e:
        print("Trends unavailable:", e)
        return {}


def latest():
    rows = db.q("SELECT slug, interest FROM trends t WHERE ts=(SELECT MAX(ts) FROM trends WHERE slug=t.slug)")
    return {r["slug"]: r["interest"] for r in rows}
