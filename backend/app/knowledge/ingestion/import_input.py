"""Parse bulk paste input without turning headings into URLs."""
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


def normalize_hostname(host: str) -> str:
    return host.lower().rstrip(".").removeprefix("www.")


def normalize_article_url(value: str, internal_hosts: set[str] | None = None) -> str:
    parsed = urlsplit(value.strip())
    host = normalize_hostname(parsed.hostname or "")
    if parsed.scheme.lower() not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("略過非完整公開 HTTP(S) 網址")
    if host == "localhost" or host.endswith((".localhost", ".local")) or host in (internal_hosts or set()):
        raise ValueError("略過站內或本機網址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("略過私人網路或回送位址")
    port = parsed.port
    netloc = f"[{host}]" if ":" in host else host
    if port and not (parsed.scheme.lower() == "https" and port == 443 or parsed.scheme.lower() == "http" and port == 80):
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def allowed_domain(url: str, domains: set[str]) -> bool:
    host = normalize_hostname(urlsplit(url).hostname or "")
    return any(host == normalize_hostname(domain) or host.endswith("." + normalize_hostname(domain)) for domain in domains)


def parse_import_input(text: str) -> list[tuple[str, str]]:
    entries = []
    category = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            category = line.lstrip("#").strip()
            continue
        links = re.findall(r"\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", line)
        if links:
            entries.extend((url, category) for url in links)
            continue
        urls = re.findall(r"https?://[^\s<>]+", line)
        if urls:
            entries.extend((url.rstrip("。，,;"), category) for url in urls)
        else:
            entries.append((line, category))
            if not line.startswith(("/", "./", "../")):
                category = line.strip("* ")
    return entries
