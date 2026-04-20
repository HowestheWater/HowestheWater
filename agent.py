"""
Competitor Discount Agent for HowestheWater.

Scrapes competitor sites and our own site to compare discount offerings,
then generates an actionable gap analysis report.

Usage:
    pip install -r requirements.txt
    cp .env.example .env          # add your ANTHROPIC_API_KEY
    python agent.py

    # Override sites at runtime:
    python agent.py --our-url https://howesthewater.com \
                    --competitor "CompA|https://compa.com" \
                    --competitor "CompB|https://compb.com"
"""

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime
from urllib.parse import urljoin, urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import config as cfg

load_dotenv()

# ── HTTP helpers ──────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch(url: str, timeout: int = 12) -> requests.Response | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r
    except requests.RequestException:
        return None


def _clean_text(soup: BeautifulSoup, max_chars: int = 6000) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "img"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text[:max_chars]


# ── Tool implementations ───────────────────────────────────────────────────────


def scrape_url(url: str) -> dict:
    """Return cleaned page content for a given URL."""
    resp = _fetch(url)
    if resp is None:
        return {"url": url, "status": "error", "error": "Request failed or timed out"}

    soup = BeautifulSoup(resp.content, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    description = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""
    content = _clean_text(soup)

    return {
        "url": url,
        "status": "success",
        "title": title,
        "description": description,
        "content": content,
    }


def find_discount_links(base_url: str) -> dict:
    """
    Scrape the homepage and sitemap to find links that likely lead to
    discount, deals, or pricing pages.
    """
    keyword_set = {kw.lower() for kw in cfg.DISCOUNT_KEYWORDS}
    found: list[str] = []
    checked_urls = {base_url.rstrip("/")}

    # Pages to inspect for internal links
    candidates = [base_url, urljoin(base_url, "/sitemap.xml")]

    for start in candidates:
        resp = _fetch(start, timeout=10)
        if resp is None:
            continue

        content_type = resp.headers.get("content-type", "")
        if "xml" in content_type:
            # Parse sitemap
            soup = BeautifulSoup(resp.content, "lxml-xml")
            locs = [tag.get_text(strip=True) for tag in soup.find_all("loc")]
            for loc in locs:
                if any(kw in loc.lower() for kw in keyword_set):
                    normalized = loc.rstrip("/")
                    if normalized not in checked_urls:
                        checked_urls.add(normalized)
                        found.append(loc)
        else:
            # Parse HTML for anchor tags
            soup = BeautifulSoup(resp.content, "lxml")
            base_domain = urlparse(base_url).netloc
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith(("#", "mailto:", "tel:")):
                    continue
                full = urljoin(base_url, href).rstrip("/")
                if urlparse(full).netloc != base_domain:
                    continue
                anchor_text = a.get_text(strip=True).lower()
                path_lower = urlparse(full).path.lower()
                if any(kw in anchor_text or kw in path_lower for kw in keyword_set):
                    if full not in checked_urls:
                        checked_urls.add(full)
                        found.append(full)

    # De-duplicate, keep first 8
    seen: set[str] = set()
    unique: list[str] = []
    for url in found:
        if url not in seen:
            seen.add(url)
            unique.append(url)
        if len(unique) >= 8:
            break

    return {"base_url": base_url, "discount_links": unique}


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "scrape_url",
        "description": (
            "Fetch and return the cleaned text content of a webpage. "
            "Use this to read pricing pages, promotion pages, and any other "
            "pages that may contain discount or offer information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to scrape"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "find_discount_links",
        "description": (
            "Scan a website's homepage and sitemap to discover URLs that "
            "are likely related to discounts, deals, promotions, or pricing. "
            "Returns a list of candidate URLs to scrape next."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the website (e.g. https://example.com)",
                },
            },
            "required": ["base_url"],
        },
    },
]


def _dispatch_tool(name: str, tool_input: dict) -> str:
    if name == "scrape_url":
        return json.dumps(scrape_url(tool_input["url"]), ensure_ascii=False)
    if name == "find_discount_links":
        return json.dumps(find_discount_links(tool_input["base_url"]), ensure_ascii=False)
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Agent ──────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""
    You are a competitive-intelligence analyst for a water delivery company.

    Your goal is to compare discounts and promotional offers between our company
    (HowestheWater) and the listed competitors.

    Process:
    1. For each site (ours first, then competitors), call find_discount_links to
       discover promotion or pricing pages.
    2. Call scrape_url on the homepage AND each discovered discount page.
    3. Extract every concrete discount or promotional offer you find:
       - Percentage discounts (e.g. "20% off first order")
       - Dollar-off amounts (e.g. "$10 off")
       - Free trials or free months
       - Subscription/recurring discounts
       - Referral bonuses
       - Seasonal or limited-time offers
       - Bundle deals
       - New-customer incentives
    4. After gathering all data, write a clear, structured report with:
       a. Summary table: site vs. offer types found
       b. Detailed breakdown per site
       c. Gap analysis: what competitors offer that we do not
       d. Actionable recommendations for HowestheWater

    Be thorough — scrape every relevant page you find.
    If a page fails to load, note it and continue.
    Do NOT fabricate offers; only report what you actually read from the pages.
""").strip()


def build_initial_message(our_site: dict, competitors: list[dict]) -> str:
    lines = [
        "Analyze discount offerings for the following websites:\n",
        f"**Our site:** {our_site['name']}  —  {our_site['base_url']}",
        "",
        "**Competitors:**",
    ]
    for c in competitors:
        lines.append(f"- {c['name']}  —  {c['base_url']}")
    lines += [
        "",
        "Start by finding discount pages on each site, scrape them, then produce "
        "a comprehensive gap-analysis report.",
    ]
    return "\n".join(lines)


def run_agent(our_site: dict, competitors: list[dict], save_report: bool = True) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [
        {"role": "user", "content": build_initial_message(our_site, competitors)}
    ]

    print("━" * 64)
    print(" HowestheWater — Competitor Discount Agent")
    print("━" * 64)

    final_text = ""
    iteration = 0
    max_iterations = 30  # guard against runaway loops

    while iteration < max_iterations:
        iteration += 1

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect tool-use blocks and any text
        tool_use_blocks = []
        for block in response.content:
            if block.type == "thinking":
                pass  # internal reasoning; not printed
            elif block.type == "text" and block.text.strip():
                print(block.text)
                final_text = block.text
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            print(f"[agent] Unexpected stop_reason: {response.stop_reason}")
            break

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools
        tool_results = []
        for tu in tool_use_blocks:
            label = tu.input.get("url") or tu.input.get("base_url") or ""
            print(f"\n[{tu.name}] {label}")
            result_str = _dispatch_tool(tu.name, tu.input)

            # Print a brief preview
            try:
                result_obj = json.loads(result_str)
                if "discount_links" in result_obj:
                    links = result_obj["discount_links"]
                    print(f"  → found {len(links)} discount link(s)")
                elif result_obj.get("status") == "error":
                    print(f"  → error: {result_obj.get('error')}")
                else:
                    chars = len(result_obj.get("content", ""))
                    print(f"  → scraped {chars} chars")
            except Exception:
                pass

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    print("\n" + "━" * 64)

    if save_report and final_text:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"discount_report_{timestamp}.txt"
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(final_text)
        print(f"Report saved → {report_path}")

    return final_text


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="HowestheWater competitor discount agent"
    )
    parser.add_argument(
        "--our-url",
        default=cfg.OUR_SITE["base_url"],
        help="Our website URL (overrides config.py)",
    )
    parser.add_argument(
        "--our-name",
        default=cfg.OUR_SITE["name"],
        help="Our company name (overrides config.py)",
    )
    parser.add_argument(
        "--competitor",
        action="append",
        metavar="NAME|URL",
        help='Add a competitor as "Name|https://url.com". Repeatable.',
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save the report to a file",
    )
    args = parser.parse_args()

    our_site = {"name": args.our_name, "base_url": args.our_url}

    if args.competitor:
        competitors = []
        for entry in args.competitor:
            parts = entry.split("|", 1)
            if len(parts) != 2:
                sys.exit(f"Invalid --competitor format: '{entry}'. Use 'Name|https://url'")
            competitors.append({"name": parts[0].strip(), "base_url": parts[1].strip()})
    else:
        competitors = cfg.COMPETITOR_SITES

    run_agent(our_site, competitors, save_report=not args.no_save)


if __name__ == "__main__":
    main()
