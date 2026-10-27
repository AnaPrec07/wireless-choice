"""The autonomous loop. Everything it produces is a draft awaiting human approval."""
import asyncio
import traceback

from . import catalog, content, db, insights, social
from .config import settings
from .connectors import trends


def run_once():
    log = []
    try:
        catalog.seed()
        log.append(f"trends: {len(trends.refresh())} products")
        log.append(f"reviews ingested: {insights.ingest()}")
        for p in catalog.all_products():
            insights.build(p["slug"])
        log.append("insights rebuilt")
        ids = content.generate_all()
        log.append(f"drafts created: {len(ids)} (awaiting approval)")
        if settings.auto_publish:
            log.append(f"published approved: {social.publish_approved()}")
    except Exception:
        log.append("ERROR\n" + traceback.format_exc())
    db.x("INSERT INTO runs(ts,log) VALUES(?,?)", (db.now(), "\n".join(log)))
    return log


async def loop():
    if settings.interval_hours <= 0:
        return
    while True:
        await asyncio.to_thread(run_once)
        await asyncio.sleep(settings.interval_hours * 3600)
