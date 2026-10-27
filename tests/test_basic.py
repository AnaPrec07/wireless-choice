import os, tempfile
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ.update(ADMIN_PASSWORD="pw", AMAZON_ASSOCIATE_TAG="t-20", ENABLE_TRENDS="0", PIPELINE_INTERVAL_HOURS="0",
                  ANTHROPIC_API_KEY="", YOUTUBE_API_KEY="")
from fastapi.testclient import TestClient
from wirelesschoice import content, pipeline, db
from wirelesschoice.web import app


def test_end_to_end():
    with TestClient(app) as c:
        assert "ERROR" not in "\n".join(pipeline.run_once())
        assert c.get("/").status_code == 200
        r = c.get("/recommend", params={"need": "running at the gym"})
        assert r.status_code == 200 and "Shokz" in r.text
        r = c.get("/go/sony-wh-1000xm5", follow_redirects=False)
        assert "tag=t-20" in r.headers["location"]
        assert c.get("/admin").status_code == 401
        assert c.get("/admin", auth=("a", "pw")).status_code == 200
        assert c.get("/p/sony-wh-1000xm5").status_code == 200
        pend = db.q("SELECT * FROM content WHERE status='pending' AND kind='article'")
        assert pend and "Amazon Associate" in pend[0]["body"]
        assert "/guides" not in c.get("/").text  # unapproved content is not public
        bad = c.post(f"/admin/{pend[0]['id']}/approve", auth=("a", "pw"), data={"body": "costs $99"})
        assert bad.status_code == 400  # flagged text cannot be approved
        ok = c.post(f"/admin/{pend[0]['id']}/approve", auth=("a", "pw"),
                    data={"body": "Fine text.\n\nAs an Amazon Associate we earn from qualifying purchases."}, follow_redirects=False)
        assert ok.status_code == 303
        assert c.get("/p/" + pend[0]["slug"]).text.count("Fine text") == 1


def test_compliance():
    assert content.compliance("x", "Great buy for $99", "social")
    assert not content.compliance("x", "Nice insight https://x #ad", "social")
