"""AI content engine: guides, social posts and ad strategy. Everything lands in the approval queue as
'pending'; nothing is public or posted until a human approves it. A compliance check flags risky drafts."""
import json
import re

from . import catalog, db, insights, llm
from .config import DISCLOSURE, SHORT_DISCLOSURE, settings

VOICE = ("You write for an independent headphone buying-guide site. Honest, specific, friendly, no hype. "
         "Use ONLY facts supplied. Never state prices, discounts, star ratings or specs not given. "
         "Never claim hands-on testing; say 'based on what owners report'. Never write 'guaranteed' or 'best ever'.")
CHANNELS = {"x": 270, "bluesky": 290, "instagram": 1800, "pinterest": 480, "tiktok": 900}


def compliance(channel, body, kind="social"):
    """Return list of issues; empty means OK."""
    issues = []
    if kind == "article" and "Amazon Associate" not in body:
        issues.append("missing Amazon Associates disclosure")
    if kind == "social" and not re.search(r"#ad|affiliate", body, re.I):
        issues.append("missing #ad / affiliate disclosure")
    if re.search(r"\$\s?\d|\d+\s?(usd|dollars)|% off|discount|deal ends", body, re.I):
        issues.append("contains price/discount claim (not allowed unless sourced live from Amazon)")
    if re.search(r"guarantee|best ever|cure|miracle|#1\b", body, re.I):
        issues.append("unsubstantiated superlative")
    lim = CHANNELS.get(channel)
    if lim and len(body) > lim:
        issues.append(f"too long for {channel} ({len(body)}>{lim})")
    return issues


def _save(kind, channel, slug, title, body, meta=None):
    flags = "; ".join(compliance(channel, body, kind))
    return db.x("INSERT INTO content(kind,channel,slug,title,body,meta,status,flags,created) VALUES(?,?,?,?,?,?,?,?,?)",
                (kind, channel, slug, title, body, json.dumps(meta or {}), "pending", flags, db.now()))


def article_for(slug):
    p, ins = catalog.get(slug), insights.get(slug) or insights.build(slug)
    facts = (f"{p['name']} ({p['form']}, ANC={'yes' if p['anc'] else 'no'}, {p['tier']} price tier). {p['blurb']} "
             f"Pros: {p['pros']}. Cons: {p['cons']}. Owner feedback summary: {ins.get('summary') or 'n/a'}. "
             f"Aspect sentiment (-1..1): { {k: v['sentiment'] for k, v in ins['aspects'].items()} }")
    body = llm.complete(VOICE, f"Write a 400-word markdown buying guide section about this product with H2 headings "
                        f"('Who it's for', 'What owners like', 'What to watch out for', 'Verdict').\nFacts: {facts}", 1200)
    if not body:
        body = (f"## Who it's for\n{p['blurb']}\n\n## What owners like\n" + "\n".join(f"- {x}" for x in p["pros"]) +
                "\n\n## What to watch out for\n" + "\n".join(f"- {x}" for x in p["cons"]) +
                "\n\n## Verdict\nA solid pick if the strengths above match your priorities.\n")
    body += f"\n\n[Check the current price on Amazon]({catalog.go_url(slug, 'guide')})\n\n*{DISCLOSURE}*"
    if ins.get("demo"):
        body = "> ⚠️ Draft generated from demo data. Connect YouTube/API keys before approving.\n\n" + body
    return _save("article", "site", slug, f"{p['name']}: is it right for you?", body, {"demo": ins.get("demo")})


def social_for(slug, channels=("x", "instagram", "pinterest", "tiktok")):
    p, ins = catalog.get(slug), insights.get(slug) or insights.build(slug)
    ids = []
    for ch in channels:
        link = catalog.go_url(slug, ch)
        text = llm.complete(
            VOICE, f"Write one {ch} post (max {CHANNELS[ch] - 80} characters excluding link and hashtags) about "
            f"{p['name']}: {p['blurb']} Pros: {p['pros']}. Cons: {p['cons']}. Lead with one useful insight; "
            f"be honest about one drawback. {'Write as a 30s spoken script with a hook.' if ch == 'tiktok' else ''} "
            f"No emojis spam, max 2 hashtags.", 400)
        text = text or f"{p['name']}: {p['pros'][0]}. Worth knowing: {p['cons'][0]}."
        body = f"{text.strip()}\n\n{link}\n{SHORT_DISCLOSURE}"
        ids.append(_save("social", ch, slug, f"{ch}: {p['name']}", body))
    return ids


def ad_strategy():
    top = db.q("SELECT slug, COUNT(*) c FROM clicks GROUP BY slug ORDER BY c DESC LIMIT 5")
    cat = ", ".join(p["name"] for p in catalog.all_products())
    plan = llm.complete(
        VOICE + " You are also a performance-marketing strategist for Amazon Associates sites.",
        f"Site: {settings.site_name}. Monthly ad budget cap: ${settings.ad_budget:.0f}. Catalog: {cat}. "
        f"Top clicked: {top}.\nProduce a markdown strategy: 1) Audience segments 2) Organic social calendar (4 weeks) "
        f"3) SEO content plan 4) Paid test plan (Google Search + Meta + Pinterest) with budget split, KPIs "
        f"(EPC, conversion rate, ROAS) and kill rules 5) Compliance checklist (Amazon Associates Operating Agreement: "
        f"no Amazon links in paid ads that send traffic directly to Amazon; send to our site; disclose affiliate "
        f"relationship; no cached prices). 6) 5 Google RSA ad drafts (headlines ≤30 chars, descriptions ≤90 chars) "
        f"pointing to our own landing pages.", 2200)
    if not plan:
        plan = FALLBACK_PLAN.format(budget=settings.ad_budget)
    return _save("strategy", "ads", "", f"Ad & growth strategy ({settings.site_name})", plan)


FALLBACK_PLAN = """## Growth strategy (template; set ANTHROPIC_API_KEY for a tailored plan)
**Budget cap:** ${budget:.0f}/month (app never spends money; you launch campaigns manually).

1. **Organic first.** 3-4 approved posts/week across Pinterest, Instagram Reels/TikTok, X/Bluesky. Each leads with one insight from owner feedback and links to our site (not directly to Amazon).
2. **SEO.** One approved guide per trending model per week; target "X vs Y" and "best headphones for <use>" queries.
3. **Paid tests (only after organic traction).** Search ads on "<model> review" to our guide pages. Start at 10% of cap, kill any ad group with EPC < CPC after 100 clicks.
4. **Compliance.** Disclose affiliate links; never show cached Amazon prices; do not run ads whose destination is an Amazon page; read the current Operating Agreement before launching ads.
"""


def generate_all(max_articles=2, max_social=2):
    """Pick trending/under-covered products and draft content. Returns list of created ids."""
    from .connectors import trends
    tr = trends.latest()
    covered = {r["slug"] for r in db.q("SELECT slug FROM content WHERE kind='article'")}
    ranked = sorted(catalog.all_products(), key=lambda p: -tr.get(p["slug"], 50))
    created = []
    for p in [p for p in ranked if p["slug"] not in covered][:max_articles]:
        created.append(article_for(p["slug"]))
    soc_covered = [r["slug"] for r in db.q("SELECT slug FROM content WHERE kind='social' ORDER BY created DESC LIMIT 20")]
    for p in [p for p in ranked if p["slug"] not in soc_covered][:max_social]:
        created += social_for(p["slug"])
    wk = db.one("SELECT 1 FROM content WHERE kind='strategy' AND created>?", (db.now() - 7 * 86400,))
    if not wk:
        created.append(ad_strategy())
    return created
