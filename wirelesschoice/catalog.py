import json
from pathlib import Path
from urllib.parse import quote_plus

from . import db
from .config import settings


def seed():
    """Idempotently load the editorial catalog. To add products, edit data/catalog.json
    (optionally add an "asin" for direct /dp/ links)."""
    items = json.loads((Path(__file__).parent / "data" / "catalog.json").read_text())
    with db.tx() as c:
        for p in items:
            c.execute("INSERT OR REPLACE INTO products VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (p["slug"], p["name"], p["brand"], p["form"], p["anc"], p["tier"], p.get("asin", ""),
                       p["blurb"], json.dumps(p["pros"]), json.dumps(p["cons"])))


def _hydrate(r):
    r["pros"], r["cons"] = json.loads(r["pros"]), json.loads(r["cons"])
    return r


def all_products():
    return [_hydrate(r) for r in db.q("SELECT * FROM products ORDER BY name")]


def get(slug):
    r = db.one("SELECT * FROM products WHERE slug=?", (slug,))
    return _hydrate(r) if r else None


def amazon_url(p):
    """Associates-compliant link. We never scrape or cache Amazon prices (against the Operating Agreement);
    the visitor sees live price on Amazon."""
    tag = f"tag={settings.associate_tag}" if settings.associate_tag else ""
    if p.get("asin"):
        return f"https://www.amazon.com/dp/{p['asin']}" + (f"?{tag}" if tag else "")
    return f"https://www.amazon.com/s?k={quote_plus(p['name'])}" + (f"&{tag}" if tag else "")


def go_url(slug, src="site"):
    return f"{settings.site_url}/go/{slug}?src={src}"
