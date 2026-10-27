# WirelessChoice

AI-run headphone recommendation site that earns through the **Amazon Associates** program. The app researches,
drafts and schedules; **you review and approve**. Nothing is published, posted or spent without your approval.

## How it works
1. **Signals**: Google Trends (pytrends) + YouTube Data API v3 comments (official API only, spam/PII filtered).
2. **Vector store**: reviews are embedded (Voyage if keyed, else local hashing embedder) and stored in SQLite; cosine search powers both insights and recommendations.
3. **Insights**: per-product aspect sentiment (sound, comfort, battery, ANC, calls, value, durability) + Claude summary.
4. **Recommender**: free-text need ("quiet commute") → vector match against owner evidence + constraints + trend nudge; Claude explains picks.
5. **Content engine**: guides, social posts (X, Bluesky, Instagram, Pinterest, TikTok script) and a growth/ad strategy, all as drafts in `/admin`.
6. **Compliance gate**: drafts without disclosure, with price/discount claims or superlatives are flagged and cannot be approved until edited.
7. **Scheduler**: runs the pipeline every `PIPELINE_INTERVAL_HOURS`. Approved Bluesky posts auto-publish (`AUTO_PUBLISH_APPROVED=1`); other channels are "ready" to copy-paste (their APIs require app review).

## Run
```
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # add your Associates tag, ADMIN_PASSWORD, API keys
uvicorn wirelesschoice.web:app --reload
```
Site: `/` · Admin: `/admin` (HTTP basic, any username) · Tests: `pytest`.
Without API keys it runs in **demo mode** (synthetic placeholder reviews, template text) and labels it as such.

## Amazon Associates: staying legal
- Sign up at affiliate-program.amazon.com; use your store ID as `AMAZON_ASSOCIATE_TAG`. Your site needs to be live and you need qualifying sales within 180 days to keep the account.
- Disclosure is in every page footer, every article and every social post (`#ad`).
- **No prices are shown or cached** (Operating Agreement); visitors see live prices on Amazon. Add the Amazon Creators/PA API later if you want live prices.
- Links are `rel="sponsored nofollow"` and go through `/go/<slug>` for click stats.
- Don't send paid ads directly to Amazon pages, and don't post affiliate links in email/offline; re-read the current Operating Agreement before launching ads.
- Catalog is editorial (`wirelesschoice/data/catalog.json`); add products there (optionally with `asin`). Verify blurbs before approving anything. Specs are intentionally qualitative.
- FTC (US) / ASA (UK) require clear AI-and-affiliate transparency; `/about` explains this.

## Ads strategy
Generated weekly into the queue (organic calendar, SEO plan, paid test plan, kill rules, RSA drafts). The app **never spends money**; `MONTHLY_AD_BUDGET_USD` is only a planning cap.

## Deploy
Any container host (Fly.io, Render, Railway) running uvicorn; mount a volume for `DB_PATH`.
