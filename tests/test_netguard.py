import asyncio

from tests import mock

mock.install(settings_patch=False)


def test_local_and_odd_addresses_are_refused():
    from airag.netguard import check_sync, MESSAGE
    for url in ["http://127.0.0.1:8799/api/settings", "http://localhost/", "http://[::1]/", "http://192.168.1.1/admin",
                "http://10.0.0.5/", "http://172.16.3.4/", "http://169.254.169.254/latest/meta-data/", "http://100.64.0.1/",
                "http://router/", "http://nas.local/", "http://2130706433/", "http://0x7f.1/", "http://127.1/",
                "http://[::ffff:127.0.0.1]/", "http://[fd00::1]/", "http://0.0.0.0:11434/api/tags"]:
        assert check_sync(url) == MESSAGE, url


def test_other_schemes_and_credentials_are_refused():
    from airag.netguard import check_sync
    for url in ["file:///C:/Users/me/secrets.txt", "ftp://example.com/x", "javascript:alert(1)", "data:text/html,hi",
                "https://user:pass@example.com/"]:
        assert check_sync(url), url


def test_public_addresses_pass_and_the_setting_allows_local():
    from airag.netguard import check_sync
    assert check_sync("https://8.8.8.8/") is None
    assert check_sync("http://192.168.1.1/", allow_local=True) is None
    assert check_sync("file:///etc/passwd", allow_local=True)        # never, setting or not


def test_fetch_page_never_reads_local_addresses():
    from airag import fetch
    real = getattr(fetch, "real_fetch_page", fetch.fetch_page)      # the mock replaces fetch_page
    page = asyncio.run(real("http://127.0.0.1:1/api/history", {"fetcher": "http"}))
    assert not page.ok and page.error.startswith("Not read")


def test_api_refuses_other_sites_and_frames():
    from fastapi.testclient import TestClient
    mock.install()
    from airag.main import app
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.get("/")
        assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert c.post("/api/app/show", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        assert c.get("/api/app/ping", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        assert c.get("/api/app/ping").status_code == 200
