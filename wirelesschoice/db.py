import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  slug TEXT PRIMARY KEY, name TEXT, brand TEXT, form TEXT, anc INTEGER, tier TEXT,
  asin TEXT, blurb TEXT, pros TEXT, cons TEXT);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY, slug TEXT, source TEXT, url TEXT, text TEXT UNIQUE,
  sentiment REAL, emb BLOB, ts REAL);
CREATE TABLE IF NOT EXISTS trends(slug TEXT, interest REAL, ts REAL);
CREATE TABLE IF NOT EXISTS insights(slug TEXT PRIMARY KEY, data TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS content(
  id INTEGER PRIMARY KEY, kind TEXT, channel TEXT, slug TEXT, title TEXT, body TEXT,
  meta TEXT DEFAULT '{}', status TEXT DEFAULT 'pending', flags TEXT DEFAULT '',
  created REAL, decided REAL, published REAL);
CREATE TABLE IF NOT EXISTS clicks(id INTEGER PRIMARY KEY, slug TEXT, src TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, ts REAL, log TEXT);
"""

_lock = threading.RLock()
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def reset():
    global _conn
    if _conn:
        _conn.close()
    _conn = None


@contextmanager
def tx():
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def x(sql, args=()):
    with tx() as c:
        return c.execute(sql, args).lastrowid


def now():
    return time.time()


def jloads(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default
