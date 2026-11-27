import httpx
import pytest

from app.config import settings
from app.tools import fetch
from app.tools.fetch import FetchError, check_url, fetch_page, parse_html

PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
    ],
)
def test_blocks_private_and_loopback_addresses(url):
    with pytest.raises(FetchError, match="not a public address"):
        check_url(url)


def test_blocks_hostnames_that_resolve_to_private_ips(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", lambda host: ["10.1.2.3"])
    with pytest.raises(FetchError, match="not a public"):
        check_url("http://internal.example.com/")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"])
def test_blocks_non_http_schemes(url):
    with pytest.raises(FetchError, match="http"):
        check_url(url)


def test_allows_public_hosts(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", PUBLIC)
    check_url("https://example.com/page")


def test_private_hosts_can_be_enabled_for_local_development(monkeypatch):
    monkeypatch.setattr(settings, "allow_private_hosts", True)
    check_url("http://127.0.0.1:8080/")


HTML = """<html><head><title>Solid state battery - Wikipedia</title></head><body>
<nav><p>Navigation menu that should never be read by the agent.</p></nav>
<h1>Solid state battery</h1>
<p>A solid state battery uses solid electrodes and a solid electrolyte.<sup>[1]</sup></p>
<table><tr><td><p>Infobox cell that must be skipped entirely.</p></td></tr></table>
<script>var tracking = "ignore me please, this is a script";</script>
<ul><li>Higher energy density is the main attraction for car makers.</li></ul>
<p>tiny</p></body></html>"""


def test_parse_html_keeps_content_and_drops_noise():
    page = parse_html(HTML, "https://en.wikipedia.org/wiki/x")
    assert page.title == "Solid state battery"
    assert "solid electrolyte" in page.text
    assert "Higher energy density" in page.text
    for junk in ("Navigation", "Infobox", "tracking", "tiny", "[1]"):
        assert junk not in page.text


def _transport(handler):
    return httpx.MockTransport(handler)


def test_fetch_page_reads_html(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", PUBLIC)
    handler = lambda req: httpx.Response(200, text=HTML, headers={"content-type": "text/html"})  # noqa: E731
    page = fetch_page("https://example.com/a", transport=_transport(handler))
    assert "solid electrolyte" in page.text


def test_fetch_page_rejects_unsupported_content_type(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", PUBLIC)
    handler = lambda req: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})  # noqa: E731
    with pytest.raises(FetchError, match="content type"):
        fetch_page("https://example.com/a.pdf", transport=_transport(handler))


def test_fetch_page_reports_http_errors(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", PUBLIC)
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_page("https://example.com/", transport=_transport(lambda r: httpx.Response(404)))


def test_redirect_to_private_address_is_blocked(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", lambda host: ["10.0.0.1"] if host == "internal" else ["93.184.216.34"])

    def handler(req):
        return httpx.Response(302, headers={"location": "http://internal/secret"})

    with pytest.raises(FetchError, match="not a public"):
        fetch_page("https://example.com/redirect", transport=_transport(handler))


def test_redirect_loops_are_bounded(monkeypatch):
    monkeypatch.setattr(fetch, "_resolve", PUBLIC)
    handler = lambda req: httpx.Response(302, headers={"location": "https://example.com/loop"})  # noqa: E731
    with pytest.raises(FetchError, match="redirects"):
        fetch_page("https://example.com/loop", transport=_transport(handler))
