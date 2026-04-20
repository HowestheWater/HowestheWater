"""
Competitor Discount Agent for Vineyard Vines.

Scrapes competitor and our own site to compare discounts by category,
then renders a self-contained HTML dashboard report.

Usage:
    pip install -r requirements.txt
    cp .env.example .env          # add your ANTHROPIC_API_KEY
    python agent.py

    # Override sites at runtime:
    python agent.py --our-url https://vineyardvines.com \\
                    --competitor "J.Crew|https://www.jcrew.com" \\
                    --competitor "Lululemon|https://www.lululemon.com"
"""

import argparse
import json
import os
import sys
import textwrap
import webbrowser
from datetime import datetime
from urllib.parse import urljoin, urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import config as cfg
import dashboard as dash

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

    candidates = [base_url, urljoin(base_url, "/sitemap.xml")]

    for start in candidates:
        resp = _fetch(start, timeout=10)
        if resp is None:
            continue

        content_type = resp.headers.get("content-type", "")
        if "xml" in content_type:
            soup = BeautifulSoup(resp.content, "lxml-xml")
            locs = [tag.get_text(strip=True) for tag in soup.find_all("loc")]
            for loc in locs:
                if any(kw in loc.lower() for kw in keyword_set):
                    normalized = loc.rstrip("/")
                    if normalized not in checked_urls:
                        checked_urls.add(normalized)
                        found.append(loc)
        else:
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

# JSON schema for the category_discounts items used inside generate_dashboard
_CATEGORY_DISCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": (
                "Category name, e.g. Men's, Women's, Kids, Boys, Girls, "
                "Accessories, Footwear, Home & Gifts, Sale / Clearance"
            ),
        },
        "max_discount_pct": {
            "type": "integer",
            "description": "Highest discount percentage found in this category (0 if none)",
        },
        "active_offers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exact offer strings found for this category",
        },
    },
    "required": ["category", "max_discount_pct", "active_offers"],
}

_SITE_WIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "email_signup": {
            "type": ["string", "null"],
            "description": "Email sign-up discount offer, e.g. '15% off first order' or null",
        },
        "free_shipping": {
            "type": ["string", "null"],
            "description": "Free shipping offer, e.g. 'Free on orders $125+' or null",
        },
        "loyalty_program": {
            "type": ["string", "null"],
            "description": "Loyalty / rewards program name or description, or null",
        },
        "promo_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any promo codes visibly displayed on the site",
        },
    },
    "required": ["email_signup", "free_shipping", "loyalty_program", "promo_codes"],
}

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
    {
        "name": "generate_dashboard",
        "description": (
            "Call this ONCE at the very end after scraping all sites. "
            "Provide the fully structured discount data you collected. "
            "This will render the HTML dashboard and save the report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brands": {
                    "type": "array",
                    "description": "One entry per brand, including Vineyard Vines (is_ours=true)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "url": {"type": "string"},
                            "is_ours": {
                                "type": "boolean",
                                "description": "true only for Vineyard Vines",
                            },
                            "category_discounts": {
                                "type": "array",
                                "items": _CATEGORY_DISCOUNT_SCHEMA,
                                "description": (
                                    "One entry per clothing/product category found. "
                                    "Always include Men's, Women's, Kids if the site has them. "
                                    "Also include Accessories, Footwear, Sale/Clearance, etc. if present."
                                ),
                            },
                            "site_wide": _SITE_WIDE_SCHEMA,
                        },
                        "required": ["name", "url", "is_ours", "category_discounts", "site_wide"],
                    },
                },
                "analysis_summary": {
                    "type": "string",
                    "description": "2-4 sentence narrative summary of the overall competitive picture",
                },
                "gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Each gap where a competitor outperforms Vineyard Vines. "
                        "Be specific — name the competitor, the category, and the offer difference."
                    ),
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete, actionable steps Vineyard Vines should take to close gaps",
                },
            },
            "required": ["brands", "analysis_summary", "gaps", "recommendations"],
        },
    },
]


# ── Tool dispatch ──────────────────────────────────────────────────────────────

# Holds the structured data Claude passes to generate_dashboard
_dashboard_data: dict | None = None


def _dispatch_tool(name: str, tool_input: dict) -> str:
    global _dashboard_data
    if name == "scrape_url":
        return json.dumps(scrape_url(tool_input["url"]), ensure_ascii=False)
    if name == "find_discount_links":
        return json.dumps(find_discount_links(tool_input["base_url"]), ensure_ascii=False)
    if name == "generate_dashboard":
        _dashboard_data = tool_input
        return json.dumps({"status": "ok", "message": "Dashboard data received."})
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""
    You are a competitive-intelligence analyst for Vineyard Vines, a premium
    preppy lifestyle and apparel brand (vineyardvines.com).

    Your goal is to scrape Vineyard Vines and its listed competitors, extract
    all discount and promotional offers broken down by clothing/product category,
    then call generate_dashboard with the structured findings.

    ── SCRAPING PROCESS ──────────────────────────────────────────────────────
    For each site (Vineyard Vines first, then competitors in order):
      1. Call find_discount_links(base_url) to discover sale/promo/pricing pages.
      2. Call scrape_url on the homepage.
      3. Call scrape_url on each URL returned by find_discount_links.

    ── WHAT TO EXTRACT PER SITE ─────────────────────────────────────────────
    Category-level discounts (fill category_discounts for each brand):
      • Men's       • Women's     • Kids / Boys / Girls
      • Accessories • Footwear    • Home & Gifts
      • Sale / Clearance
    For each category record:
      - max_discount_pct: the highest % off you found (0 if none)
      - active_offers: exact strings, e.g. "Extra 40% off sale styles"

    Site-wide offers (fill site_wide for each brand):
      - email_signup: discount for joining the mailing list
      - free_shipping: threshold or always-free policy
      - loyalty_program: rewards program name/description
      - promo_codes: any codes visibly shown on the page

    ── FINAL STEP ───────────────────────────────────────────────────────────
    After ALL sites are scraped, call generate_dashboard exactly once with:
      - brands: full structured data for every brand
      - analysis_summary: 2-4 sentence narrative
      - gaps: specific gaps where competitors beat VV (name brand + category + offer)
      - recommendations: concrete actions VV should take

    Rules:
    • Only report offers you literally read on the pages — do not fabricate.
    • If a page fails to load, skip it and continue.
    • Cover all brands before calling generate_dashboard.
""").strip()


# ── Agent loop ─────────────────────────────────────────────────────────────────


def build_initial_message(our_site: dict, competitors: list[dict]) -> str:
    lines = [
        "Analyze discounts and promotions for the following websites:\n",
        f"**Our brand:** {our_site['name']}  —  {our_site['base_url']}",
        "",
        "**Competitors:**",
    ]
    for c in competitors:
        lines.append(f"- {c['name']}  —  {c['base_url']}")
    lines += [
        "",
        "Scrape every site, extract category-level discount data, then call "
        "generate_dashboard with the fully structured findings to produce the dashboard.",
    ]
    return "\n".join(lines)


def run_agent(
    our_site: dict,
    competitors: list[dict],
    save_report: bool = True,
    open_browser: bool = True,
) -> str:
    global _dashboard_data
    _dashboard_data = None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [
        {"role": "user", "content": build_initial_message(our_site, competitors)}
    ]

    print("━" * 64)
    print(" Vineyard Vines — Competitor Discount Intelligence")
    print("━" * 64)

    iteration = 0
    max_iterations = 40

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

        tool_use_blocks = []
        for block in response.content:
            if block.type == "thinking":
                pass
            elif block.type == "text" and block.text.strip():
                print(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            print(f"[agent] Unexpected stop_reason: {response.stop_reason}")
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_use_blocks:
            label = tu.input.get("url") or tu.input.get("base_url") or tu.name
            print(f"\n[{tu.name}] {label}")
            result_str = _dispatch_tool(tu.name, tu.input)

            try:
                result_obj = json.loads(result_str)
                if "discount_links" in result_obj:
                    n = len(result_obj["discount_links"])
                    print(f"  → found {n} discount link(s)")
                elif tu.name == "generate_dashboard":
                    print("  → structured data received, dashboard queued")
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

        # If generate_dashboard was just called, we can let the loop finish naturally
        if _dashboard_data is not None and response.stop_reason == "tool_use":
            # Append the tool result and do one more turn so Claude can say goodbye,
            # but we already have what we need — let the loop continue normally.
            pass

    print("\n" + "━" * 64)

    report_path = ""
    if _dashboard_data:
        html_content = dash.generate_html(_dashboard_data)
        if save_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = f"discount_dashboard_{timestamp}.html"
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(html_content)
            print(f"\n✅  Dashboard saved → {report_path}")
            if open_browser:
                abs_path = os.path.abspath(report_path)
                webbrowser.open(f"file://{abs_path}")
        return html_content
    else:
        print("\n⚠️  generate_dashboard was never called — no structured data captured.")
        return ""


# ── CLI ────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Vineyard Vines competitor discount intelligence dashboard"
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
        help="Do not save the HTML report to a file",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the dashboard in a browser",
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

    run_agent(
        our_site,
        competitors,
        save_report=not args.no_save,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
