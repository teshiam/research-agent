"""Fetch a web page and reduce it to readable text.

The agent chooses URLs, so fetching is treated as a security boundary: only http(s), only public
addresses (every redirect hop is re-checked), bounded size, and bounded time.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from ..config import settings

MAX_BYTES = 1_000_000
MAX_TEXT_CHARS = 30_000
MAX_REDIRECTS = 3


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Page:
    title: str
    url: str
    text: str


def _resolve(host: str) -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(host, None)]
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host {host}.") from exc


def check_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs can be fetched.")
    if not parts.hostname:
        raise FetchError("URL has no host.")
    if settings.allow_private_hosts:
        return
    for ip in _resolve(parts.hostname):
        addr = ipaddress.ip_address(ip.split("%")[0])
        if addr.version == 6 and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        if not addr.is_global:
            raise FetchError(f"Blocked: {parts.hostname} is not a public address.")


_SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg",
         "table", "sup", "button"}  # fmt: skip
_BLOCKS = {"p", "li", "h1", "h2", "h3"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.blocks: list[str] = []
        self._skip = 0
        self._in_title = False
        self._block: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCKS and self._skip == 0 and self._block is None:
            self._block, self._buf = tag, []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == self._block:
            text = re.sub(r"\s+", " ", "".join(self._buf)).replace("[edit]", "").strip()
            if text and (tag.startswith("h") or len(text) >= 25):
                self.blocks.append(text)
            self._block = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._block and self._skip == 0:
            self._buf.append(data)


def parse_html(markup: str, url: str) -> Page:
    parser = _Extractor()
    parser.feed(markup)
    title = re.sub(r"\s+", " ", parser.title).strip() or url
    text = "\n".join(parser.blocks)[:MAX_TEXT_CHARS]
    return Page(title=re.sub(r"\s+[-–|]\s+Wikipedia$", "", title), url=url, text=text)


def fetch_page(url: str, *, transport: httpx.BaseTransport | None = None) -> Page:
    current = url
    headers = {"User-Agent": settings.user_agent, "Accept": "text/html,text/plain"}
    with httpx.Client(timeout=15, headers=headers, transport=transport) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(current)
            try:
                with client.stream("GET", current) as res:
                    if res.is_redirect:
                        current = urljoin(current, res.headers.get("location", ""))
                        continue
                    if res.status_code >= 400:
                        raise FetchError(f"The page returned HTTP {res.status_code}.")
                    ctype = res.headers.get("content-type", "").lower()
                    if not any(t in ctype for t in ("text/html", "text/plain", "xhtml")):
                        raise FetchError(f"Unsupported content type: {ctype or 'unknown'}.")
                    raw = bytearray()
                    for chunk in res.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            break
                    markup = bytes(raw).decode(res.encoding or "utf-8", errors="replace")
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not fetch the page: {exc}") from exc
            if "text/plain" in ctype:
                return Page(title=current, url=current, text=markup[:MAX_TEXT_CHARS])
            return parse_html(markup, current)
    raise FetchError("Too many redirects.")
