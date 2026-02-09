import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

HEADERS = {"User-Agent": "Mozilla/5.0"}

def extract_real_url(possible_redirect_url: str) -> str:
    try:
        parsed = urlparse(possible_redirect_url)
        qs = parse_qs(parsed.query)

        target = qs.get("target") or qs.get("url")
        if target:
            decoded = unquote(target[0])
            if decoded.startswith("http://") or decoded.startswith("https://"):
                return decoded
    except Exception:
        pass

    return possible_redirect_url


def clean_domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").replace("www.", "")
    except:
        return ""


def get_meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"property": name})
    if not tag:
        tag = soup.find("meta", attrs={"name": name})
    return tag.get("content", "").strip() if tag and tag.get("content") else ""

def build_fallback_metadata(src, url, error=None):
    domain = clean_domain(url)

    return {
        "from": src.get("from") or domain or "Unknown Source",
        "url": url,
        "domain": domain,
        "headline": src.get("from") or domain or "Unavailable page",
        "summary": "",
    }

def extract_metadata(html: str, final_url: str, fallback_from=None):
    soup = BeautifulSoup(html, "lxml")

    domain = clean_domain(final_url)

    site_name = get_meta(soup, "og:site_name") or fallback_from or domain or "Unknown Source"

    headline = (
        get_meta(soup, "og:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else domain or "No title")
    )

    summary = (
        get_meta(soup, "og:description")
        or get_meta(soup, "description")
        or ""
    )

    return {
        "from": site_name,
        "url": final_url,
        "domain": domain,
        "headline": headline,
        "summary": summary,
    }

async def fetch_one(session, src):
    initial_url = extract_real_url(src["url"])

    try:
        async with session.get(initial_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            final_url = str(resp.url)

            if resp.status >= 400:
                return build_fallback_metadata(src, final_url, f"HTTP {resp.status}")

            html = await resp.text(errors="ignore")

        if not html or len(html) < 50:
            return build_fallback_metadata(src, final_url, "Empty response")

        return extract_metadata(html, final_url, src.get("from"))

    except asyncio.TimeoutError:
        return build_fallback_metadata(src, initial_url, "Timeout")

    except aiohttp.ClientConnectorError:
        return build_fallback_metadata(src, initial_url, "DNS/Connection failed")

    except aiohttp.ClientSSLError:
        return build_fallback_metadata(src, initial_url, "SSL error")

    except aiohttp.ClientError as err:
        return build_fallback_metadata(src, initial_url, f"Network error: {err}")

    except Exception as err:
        return build_fallback_metadata(src, initial_url, f"Parse error: {err}")


async def fetch_all_metadata(sources, concurrency=10):
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [fetch_one(session, src) for src in sources]
        results = await asyncio.gather(*tasks)

    return results


def get_metadata_parallel(sources, concurrency=10):
    return asyncio.run(fetch_all_metadata(sources, concurrency))

def get_citations_from_grounding(grounding_chunks):
    sources = []

    for chunk in grounding_chunks:
        if chunk.get("web", {}).get("uri"):
            sources.append({
                "url": chunk["web"]["uri"],
                "from": chunk["web"].get("title"),
            })

    return get_metadata_parallel(sources)
