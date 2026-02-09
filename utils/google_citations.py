import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------------------
# URL Helpers
# ---------------------------------------------------

def extract_real_url(possible_redirect_url: str) -> str:
    """
    Handles Google / tracking redirect URLs:
    example: https://google.com/url?target=https://site.com
    """
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
        return urlparse(url).hostname.replace("www.", "")
    except:
        return ""


def get_meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"property": name})
    if not tag:
        tag = soup.find("meta", attrs={"name": name})
    return tag.get("content", "").strip() if tag and tag.get("content") else ""


# ---------------------------------------------------
# Core Metadata Extraction
# ---------------------------------------------------

def extract_metadata(html: str, final_url: str, fallback_from=None):
    soup = BeautifulSoup(html, "lxml")

    domain = clean_domain(final_url)

    site_name = get_meta(soup, "og:site_name") or fallback_from or domain or "Unknown Source"

    headline = (
        get_meta(soup, "og:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else "No title found")
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


# ---------------------------------------------------
# Async Fetch
# ---------------------------------------------------

async def fetch_one(session, src):
    try:
        initial_url = extract_real_url(src["url"])

        async with session.get(initial_url, allow_redirects=True, timeout=10) as resp:
            final_url = str(resp.url)
            html = await resp.text(errors="ignore")

        return extract_metadata(html, final_url, src.get("from"))

    except Exception as err:
        print(f"Failed to fetch {src.get('url')}: {err}")
        return None


async def fetch_all_metadata(sources, concurrency=10):
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [fetch_one(session, src) for src in sources]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r]


def get_metadata_parallel(sources, concurrency=10):
    return asyncio.run(fetch_all_metadata(sources, concurrency))


# ---------------------------------------------------
# Grounding Integration (same as your earlier API)
# ---------------------------------------------------

def get_citations_from_grounding(grounding_chunks):
    sources = []

    for chunk in grounding_chunks:
        if chunk.get("web", {}).get("uri"):
            sources.append({
                "url": chunk["web"]["uri"],
                "from": chunk["web"].get("title"),
            })

    return get_metadata_parallel(sources)
