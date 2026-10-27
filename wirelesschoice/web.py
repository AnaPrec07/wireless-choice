import asyncio
import contextlib
import html
import secrets
from pathlib import Path

import markdown as md
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import catalog, content, db, insights, pipeline, recommender, social
from .config import DISCLOSURE, settings

HERE = Path(__file__).parent


@contextlib.asynccontextmanager
async def lifespan(app):
    catalog.seed()
    task = asyncio.create_task(pipeline.loop())
    yield
    task.cancel()


app = FastAPI(title="WirelessChoice", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
T = Jinja2Templates(directory=HERE / "templates")
T.env.filters["md"] = lambda s: md.markdown(html.escape(s or "", quote=False).replace("&gt;", ">"), extensions=["extra"])
T.env.globals.update(settings=settings, DISCLOSURE=DISCLOSURE, amazon_url=catalog.amazon_url)
security = HTTPBasic()


def admin(cred: HTTPBasicCredentials = Depends(security)):
    pw = settings.admin_password
    if not pw or not secrets.compare_digest(cred.password.encode(), pw.encode()):
        raise HTTPException(401, "Admin disabled or wrong password", headers={"WWW-Authenticate": "Basic"})


def page(request, name, **ctx):
    return T.TemplateResponse(request, name, ctx)


@app.get("/")
def home(request: Request):
    guides = db.q("SELECT * FROM content WHERE kind='article' AND status IN ('approved','published') ORDER BY created DESC LIMIT 6")
    return page(request, "home.html", products=catalog.all_products(), guides=guides)


@app.get("/recommend")
def recommend(request: Request, need: str = "", form: str = "", tier: str = "", anc: str = ""):
    need = need.strip()[:300]
    top = recommender.recommend(need or "great all-round headphones", form or None, tier or None,
                                {"yes": True, "no": False}.get(anc)) if need else []
    return page(request, "results.html", need=need, top=top)


@app.get("/p/{slug}")
def product(request: Request, slug: str):
    p = catalog.get(slug)
    if not p:
        raise HTTPException(404)
    guide = db.one("SELECT * FROM content WHERE kind='article' AND slug=? AND status IN ('approved','published') "
                   "ORDER BY created DESC", (slug,))
    return page(request, "product.html", p=p, ins=insights.get(slug), guide=guide)


@app.get("/go/{slug}")
def go(slug: str, src: str = "site"):
    p = catalog.get(slug)
    if not p:
        raise HTTPException(404)
    db.x("INSERT INTO clicks(slug,src,ts) VALUES(?,?,?)", (slug, src[:20], db.now()))
    return RedirectResponse(catalog.amazon_url(p), status_code=302)


@app.get("/about")
def about(request: Request):
    return page(request, "about.html")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /go/\nSitemap: {settings.site_url}/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap():
    urls = [settings.site_url + "/"] + [f"{settings.site_url}/p/{p['slug']}" for p in catalog.all_products()]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")


# ---------- admin: review & approve ----------
@app.get("/admin", dependencies=[Depends(admin)])
def admin_home(request: Request, status: str = "pending"):
    items = db.q("SELECT * FROM content WHERE status=? ORDER BY created DESC LIMIT 100", (status,))
    stats = {"clicks": db.one("SELECT COUNT(*) c FROM clicks")["c"],
             "by_slug": db.q("SELECT slug, COUNT(*) c FROM clicks GROUP BY slug ORDER BY c DESC LIMIT 5"),
             "last_run": db.one("SELECT * FROM runs ORDER BY ts DESC LIMIT 1")}
    from . import llm
    return page(request, "admin.html", items=items, status=status, stats=stats, llm_on=llm.available())


@app.post("/admin/run", dependencies=[Depends(admin)])
def admin_run():
    pipeline.run_once()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/{cid}/{action}", dependencies=[Depends(admin)])
def admin_action(cid: int, action: str, body: str = Form(None)):
    if action not in ("approve", "reject", "save"):
        raise HTTPException(400)
    it = db.one("SELECT * FROM content WHERE id=?", (cid,))
    if not it:
        raise HTTPException(404)
    if body is not None:
        flags = "; ".join(content.compliance(it["channel"], body, it["kind"]))
        db.x("UPDATE content SET body=?, flags=? WHERE id=?", (body, flags, cid))
        it["flags"] = flags
    if action == "approve":
        if it["flags"]:  # flags were recomputed from the submitted body above
            raise HTTPException(400, "Compliance flags present; fix the text first: " + it["flags"])
        db.x("UPDATE content SET status='approved', decided=? WHERE id=?", (db.now(), cid))
    elif action == "reject":
        db.x("UPDATE content SET status='rejected', decided=? WHERE id=?", (db.now(), cid))
    if action == "approve" and it["kind"] == "social":
        social.publish_approved() if settings.auto_publish else None
    return RedirectResponse("/admin", status_code=303)
