"""Vector store backed by SQLite (embeddings as float32 blobs) + numpy cosine search.
Embeddings: Voyage AI if VOYAGE_API_KEY is set, else a local feature-hashing embedder (no network)."""
import hashlib
import re

import numpy as np

from . import db
from .config import settings

DIM_LOCAL = 512
_STOP = set("the a an and or of to is it in on for with this that i my be are was as at but very so".split())


def _local(text):
    toks = [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in _STOP]
    feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
    v = np.zeros(DIM_LOCAL, dtype=np.float32)
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        v[h % DIM_LOCAL] += 1.0 if (h >> 64) & 1 else -1.0
    n = np.linalg.norm(v)
    return v / n if n else v


def embed(texts):
    if settings.voyage_key:
        try:
            import httpx
            r = httpx.post("https://api.voyageai.com/v1/embeddings", timeout=30,
                           headers={"Authorization": f"Bearer {settings.voyage_key}"},
                           json={"input": texts, "model": "voyage-3-lite"})
            r.raise_for_status()
            vs = [np.array(d["embedding"], dtype=np.float32) for d in r.json()["data"]]
            return [v / (np.linalg.norm(v) or 1) for v in vs]
        except Exception as e:
            print("Voyage failed, using local embedder:", e)
    return [_local(t) for t in texts]


def add_reviews(rows):
    """rows: dicts with slug, source, url, text, sentiment. Dedupes on text. Returns count added."""
    rows = [r for r in rows if not db.one("SELECT 1 FROM reviews WHERE text=?", (r["text"],))]
    if not rows:
        return 0
    vecs = embed([r["text"] for r in rows])
    with db.tx() as c:
        for r, v in zip(rows, vecs):
            c.execute("INSERT OR IGNORE INTO reviews(slug,source,url,text,sentiment,emb,ts) VALUES(?,?,?,?,?,?,?)",
                      (r["slug"], r["source"], r.get("url", ""), r["text"], r["sentiment"],
                       v.astype(np.float32).tobytes(), db.now()))
    return len(rows)


def search(query, k=8, slug=None):
    """Top-k reviews by cosine similarity. Skips vectors whose dimension differs from the query's."""
    qv = embed([query])[0]
    rows = db.q("SELECT id,slug,source,url,text,sentiment,emb FROM reviews" + (" WHERE slug=?" if slug else ""),
                (slug,) if slug else ())
    rows = [r for r in rows if len(r["emb"]) == qv.nbytes]
    if not rows:
        return []
    m = np.stack([np.frombuffer(r["emb"], dtype=np.float32) for r in rows])
    sims = m @ qv
    out = []
    for i in np.argsort(-sims)[:k]:
        r = {kk: vv for kk, vv in rows[i].items() if kk != "emb"}
        r["score"] = float(sims[i])
        out.append(r)
    return out
