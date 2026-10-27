import os
from pathlib import Path


def _load_dotenv():
    p = Path(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def env(name, default=""):
    return os.environ.get(name, default)


class Settings:
    @property
    def associate_tag(self): return env("AMAZON_ASSOCIATE_TAG")
    @property
    def site_name(self): return env("SITE_NAME", "WirelessChoice")
    @property
    def site_url(self): return env("SITE_URL", "http://localhost:8000").rstrip("/")
    @property
    def admin_password(self): return env("ADMIN_PASSWORD")
    @property
    def anthropic_key(self): return env("ANTHROPIC_API_KEY")
    @property
    def model(self): return env("LLM_MODEL", "claude-sonnet-5-5")
    @property
    def voyage_key(self): return env("VOYAGE_API_KEY")
    @property
    def youtube_key(self): return env("YOUTUBE_API_KEY")
    @property
    def enable_trends(self): return env("ENABLE_TRENDS", "1") == "1"
    @property
    def bluesky(self): return env("BLUESKY_HANDLE"), env("BLUESKY_APP_PASSWORD")
    @property
    def auto_publish(self): return env("AUTO_PUBLISH_APPROVED", "0") == "1"
    @property
    def interval_hours(self): return float(env("PIPELINE_INTERVAL_HOURS", "24"))
    @property
    def ad_budget(self): return float(env("MONTHLY_AD_BUDGET_USD", "0"))
    @property
    def db_path(self): return env("DB_PATH", "wirelesschoice.db")


settings = Settings()

DISCLOSURE = ("As an Amazon Associate we earn from qualifying purchases. "
              "Links on this site are affiliate links; they never change the price you pay.")
SHORT_DISCLOSURE = "#ad (affiliate link)"
