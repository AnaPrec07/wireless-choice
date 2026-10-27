"""Publishers. Only items a human approved are ever sent. Bluesky has an open API and posts directly;
Instagram/TikTok/Pinterest/X require app review or paid APIs, so those items are marked 'ready' for
one-tap manual posting (copy from the admin page)."""
import httpx

from . import db
from .config import settings


def _bluesky(text):
    handle, pw = settings.bluesky
    s = httpx.post("https://bsky.social/xrpc/com.atproto.server.createSession", timeout=20,
                   json={"identifier": handle, "password": pw})
    s.raise_for_status()
    j = s.json()
    import datetime
    r = httpx.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", timeout=20,
                   headers={"Authorization": "Bearer " + j["accessJwt"]},
                   json={"repo": j["did"], "collection": "app.bsky.feed.post",
                         "record": {"$type": "app.bsky.feed.post", "text": text[:300],
                                    "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}})
    r.raise_for_status()


def publish_approved():
    done = []
    for it in db.q("SELECT * FROM content WHERE status='approved' AND kind='social'"):
        try:
            if it["channel"] == "bluesky" and all(settings.bluesky):
                _bluesky(it["body"])
                status = "published"
            else:
                status = "ready"  # manual posting
            db.x("UPDATE content SET status=?, published=? WHERE id=?", (status, db.now(), it["id"]))
            done.append((it["id"], status))
        except Exception as e:
            print("Publish failed", it["id"], e)
    return done
