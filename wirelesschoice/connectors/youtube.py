"""YouTube Data API v3 (official; ToS compliant). Pulls top-level comments from review videos.
No scraping, no transcripts of third-party videos. Quota: search=100 units, commentThreads=1 unit."""
import re

import httpx

from ..config import settings

API = "https://www.googleapis.com/youtube/v3"
_PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://\S+|\+?\d[\d\s().-]{8,}\d")
_BAD = re.compile(r"\b(fuck|shit|bitch|cunt|nigg|retard|subscribe to my|giveaway|whatsapp|telegram|crypto)\b", re.I)


def clean(text):
    """Drop spam/toxic/very short comments; strip emails, links and phone numbers."""
    t = _PII.sub("", text or "").strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) < 40 or len(t) > 600 or _BAD.search(t):
        return None
    return t


def fetch(product_name, videos=3, per_video=40):
    if not settings.youtube_key:
        return []
    out = []
    with httpx.Client(timeout=20) as h:
        s = h.get(f"{API}/search", params={"part": "snippet", "q": f"{product_name} review", "type": "video",
                                           "maxResults": videos, "relevanceLanguage": "en",
                                           "safeSearch": "strict", "key": settings.youtube_key})
        s.raise_for_status()
        for it in s.json().get("items", []):
            vid = it["id"]["videoId"]
            c = h.get(f"{API}/commentThreads", params={"part": "snippet", "videoId": vid, "maxResults": per_video,
                                                       "order": "relevance", "textFormat": "plainText",
                                                       "key": settings.youtube_key})
            if c.status_code != 200:  # comments disabled etc.
                continue
            for th in c.json().get("items", []):
                t = clean(th["snippet"]["topLevelComment"]["snippet"]["textDisplay"])
                if t:
                    out.append({"text": t, "url": f"https://www.youtube.com/watch?v={vid}"})
    return out
