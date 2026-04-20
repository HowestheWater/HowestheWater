"""
HTML dashboard renderer for the Vineyard Vines discount intelligence report.

Accepts the structured JSON emitted by the `generate_dashboard` agent tool
and produces a single self-contained HTML file.
"""
import html as _html
from datetime import datetime


def _e(s) -> str:
    return _html.escape(str(s) if s else "")


# ── Color helpers ──────────────────────────────────────────────────────────────

def _cell_style(vv_pct: int, comp_pct: int, is_ours: bool) -> str:
    """Return inline CSS style string for a category matrix cell."""
    if is_ours:
        return "background:#EBF0FB;color:#1B3A6B;border-left:3px solid #1B3A6B;"
    if comp_pct == 0 and vv_pct == 0:
        return "background:#F5F5F5;color:#AAAAAA;"
    diff = comp_pct - vv_pct
    if diff >= 15:
        return "background:#FDECEA;color:#C62828;"   # big gap  – red
    if diff >= 5:
        return "background:#FFF3E0;color:#E65100;"   # moderate – orange
    if diff > -5:
        return "background:#FFFDE7;color:#F9A825;"   # parity   – yellow
    return "background:#E8F5E9;color:#2E7D32;"       # VV wins  – green


def _pct_label(pct: int) -> str:
    return f"{pct}%" if pct > 0 else "—"


def _tag(color: str, text: str) -> str:
    return (
        f'<span style="display:inline-block;background:{color}20;color:{color};'
        f'border:1px solid {color}40;border-radius:4px;padding:2px 7px;'
        f'font-size:10px;font-weight:600;white-space:nowrap;">{_e(text)}</span>'
    )


# ── Section builders ───────────────────────────────────────────────────────────

def _brand_cards(brands: list[dict]) -> str:
    cards = []
    for b in brands:
        is_ours = b.get("is_ours", False)
        name = b.get("name", "")
        url = b.get("url", "")
        offers_count = sum(
            len(c.get("active_offers", [])) for c in b.get("category_discounts", [])
        )
        sw = b.get("site_wide", {})
        sw_count = sum(1 for v in sw.values() if v and v != [] and v is not None)
        total = offers_count + sw_count
        max_disc = max(
            (c.get("max_discount_pct", 0) for c in b.get("category_discounts", [])),
            default=0,
        )

        border = "border-top:3px solid #E8365D;" if is_ours else "border-top:3px solid #1B3A6B;"
        cards.append(f"""
        <div class="brand-card" style="{border}">
          <div class="bc-name">{_e(name)}{"&nbsp;⭐" if is_ours else ""}</div>
          <div class="bc-url">{_e(url)}</div>
          <div class="bc-row">
            <div><span class="bc-big">{total}</span><br><span class="bc-lbl">offers found</span></div>
            <div><span class="bc-big" style="color:#E8365D;">{max_disc}%</span><br><span class="bc-lbl">max discount</span></div>
          </div>
        </div>""")
    return '<div class="brand-cards">' + "".join(cards) + "</div>"


def _category_matrix(brands: list[dict], categories: list[str]) -> str:
    our_brand = next((b for b in brands if b.get("is_ours")), None)

    # Build lookup  brand_name → category → data
    lk: dict[str, dict] = {}
    for b in brands:
        lk[b["name"]] = {c["category"]: c for c in b.get("category_discounts", [])}

    # Header row
    header_cells = ['<th class="corner">Category</th>']
    for b in brands:
        cls = ' class="ours-col"' if b.get("is_ours") else ""
        header_cells.append(f'<th{cls}>{_e(b["name"])}</th>')

    rows = []
    for cat in categories:
        vv_pct = 0
        if our_brand:
            vv_cat = lk.get(our_brand["name"], {}).get(cat, {})
            vv_pct = vv_cat.get("max_discount_pct", 0)

        cells = [f'<td class="cat-label">{_e(cat)}</td>']
        for b in brands:
            cat_data = lk.get(b["name"], {}).get(cat, {})
            pct = cat_data.get("max_discount_pct", 0)
            offers = cat_data.get("active_offers", [])
            is_ours = b.get("is_ours", False)
            style = _cell_style(vv_pct, pct, is_ours)
            short = (offers[0][:55] + "…") if offers and len(offers[0]) > 55 else (offers[0] if offers else "")
            tooltip = _e("; ".join(offers[:3]) if offers else "No discount found")
            cells.append(
                f'<td style="{style}" title="{tooltip}">'
                f'<span class="dp">{_pct_label(pct)}</span>'
                f'<span class="dd">{_e(short)}</span>'
                f"</td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    legend = """
    <div class="legend">
      <span class="leg-item"><span class="leg-dot" style="background:#EBF0FB;border:2px solid #1B3A6B;"></span>Vineyard Vines (our brand)</span>
      <span class="leg-item"><span class="leg-dot" style="background:#E8F5E9;"></span>VV leads competitor</span>
      <span class="leg-item"><span class="leg-dot" style="background:#FFFDE7;"></span>Roughly equal</span>
      <span class="leg-item"><span class="leg-dot" style="background:#FFF3E0;"></span>Competitor slightly ahead</span>
      <span class="leg-item"><span class="leg-dot" style="background:#FDECEA;"></span>Competitor significantly ahead</span>
      <span class="leg-item"><span class="leg-dot" style="background:#F5F5F5;"></span>No discount data</span>
    </div>"""

    return f"""
    <div class="matrix-wrap">
      <table class="matrix">
        <thead><tr>{"".join(header_cells)}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    {legend}"""


def _sitewide_table(brands: list[dict]) -> str:
    rows_def = [
        ("email_signup",     "Email Sign-up Offer"),
        ("free_shipping",    "Free Shipping"),
        ("loyalty_program",  "Loyalty / Rewards"),
        ("promo_codes",      "Visible Promo Codes"),
    ]

    header_cells = ['<th class="rt-label">Offer Type</th>']
    for b in brands:
        cls = ' class="ours-col"' if b.get("is_ours") else ""
        header_cells.append(f'<th{cls}>{_e(b["name"])}</th>')

    rows = []
    for key, label in rows_def:
        cells = [f'<td class="rt-type">{_e(label)}</td>']
        for b in brands:
            sw = b.get("site_wide", {})
            val = sw.get(key)
            if key == "promo_codes":
                if val:
                    codes = val if isinstance(val, list) else [val]
                    text = " · ".join(_e(c) for c in codes[:3])
                    cells.append(f'<td><span class="check">✓</span> <code style="font-size:11px;">{text}</code></td>')
                else:
                    cells.append('<td><span class="cross">—</span></td>')
            elif val:
                cells.append(f'<td><span class="check">✓</span> {_e(str(val))}</td>')
            else:
                cells.append('<td><span class="cross">—</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    return f"""
    <table class="rt">
      <thead><tr>{"".join(header_cells)}</tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def _gap_cards(gaps: list[str]) -> str:
    if not gaps:
        return '<p style="color:#888;font-size:13px;">No significant gaps identified.</p>'
    cards = []
    for i, gap in enumerate(gaps, 1):
        cards.append(f"""
        <div class="gap-card">
          <div class="gap-num">Gap #{i}</div>
          <p>{_e(gap)}</p>
        </div>""")
    return '<div class="gap-grid">' + "".join(cards) + "</div>"


def _price_intelligence_table(brands: list[dict], categories: list[str]) -> str:
    """Per-brand per-category table showing avg original → avg sale → savings."""
    # Filter to brands/categories that actually have price data
    cats_with_data = []
    for cat in categories:
        for b in brands:
            for c in b.get("category_discounts", []):
                if c.get("category", "").strip() == cat and (
                    c.get("avg_original_price") or c.get("price_examples")
                ):
                    if cat not in cats_with_data:
                        cats_with_data.append(cat)
                    break

    if not cats_with_data:
        return '<p style="color:#888;font-size:13px;">No product price data was collected for this run.</p>'

    header_cells = ['<th class="corner">Category</th>']
    for b in brands:
        cls = ' class="ours-col"' if b.get("is_ours") else ""
        header_cells.append(f'<th{cls}>{_e(b["name"])}</th>')

    rows = []
    for cat in cats_with_data:
        cells = [f'<td class="cat-label">{_e(cat)}</td>']
        for b in brands:
            cat_data = next(
                (c for c in b.get("category_discounts", [])
                 if c.get("category", "").strip() == cat),
                {},
            )
            avg_o = cat_data.get("avg_original_price")
            avg_s = cat_data.get("avg_sale_price")
            examples = cat_data.get("price_examples", [])

            if not avg_o and examples:
                avg_o = round(sum(p["original_price"] for p in examples) / len(examples), 2)
                avg_s = round(sum(p["sale_price"] for p in examples) / len(examples), 2)

            is_ours = b.get("is_ours", False)
            bg = "#EBF0FB" if is_ours else "#FAFBFC"
            border = "border-left:3px solid #1B3A6B;" if is_ours else ""
            if avg_o and avg_s:
                savings = round(avg_o - avg_s, 2)
                pct = round((avg_o - avg_s) / avg_o * 100)
                color = "#E8365D" if pct >= 20 else ("#E65100" if pct >= 10 else "#2E7D32")
                cell = (
                    f'<td style="background:{bg};{border}text-align:center;vertical-align:top;">'
                    f'<span style="display:block;font-size:11px;color:#888;">orig</span>'
                    f'<span style="font-weight:700;">${avg_o:.2f}</span>'
                    f'<span style="display:block;font-size:11px;color:#888;margin-top:4px;">sale</span>'
                    f'<span style="font-weight:700;color:{color};">${avg_s:.2f}</span>'
                    f'<span style="display:block;font-size:10px;color:{color};margin-top:3px;">'
                    f'−${savings:.2f} ({pct}% off)</span>'
                    f'</td>'
                )
            else:
                cell = f'<td style="background:{bg};{border}color:#CCC;text-align:center;">—</td>'
            cells.append(cell)
        rows.append("<tr>" + "".join(cells) + "</tr>")

    return f"""
    <div class="matrix-wrap">
      <table class="matrix">
        <thead><tr>{"".join(header_cells)}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>"""


def _winners_losers_cards(brands: list[dict], our_name: str) -> str:
    """Top deals across all brands (winners) and where VV falls behind (losers)."""
    all_examples: list[dict] = []
    for b in brands:
        for c in b.get("category_discounts", []):
            for ex in c.get("price_examples", []):
                all_examples.append({
                    **ex,
                    "brand": b["name"],
                    "category": c.get("category", ""),
                    "is_ours": b.get("is_ours", False),
                })

    if not all_examples:
        return '<p style="color:#888;font-size:13px;">No price examples collected — run with price scraping enabled.</p>'

    # Top 5 deepest discounts across all brands
    top_deals = sorted(all_examples, key=lambda x: x.get("discount_pct", 0), reverse=True)[:5]

    # VV categories where a competitor has a deeper avg discount
    our_brand = next((b for b in brands if b.get("is_ours")), None)
    loser_rows = []
    if our_brand:
        our_cats = {
            c.get("category", "").strip(): c
            for c in our_brand.get("category_discounts", [])
        }
        for cat, our_cat in our_cats.items():
            our_avg_s = our_cat.get("avg_sale_price")
            our_avg_o = our_cat.get("avg_original_price")
            our_pct = our_cat.get("max_discount_pct", 0)
            for b in brands:
                if b.get("is_ours"):
                    continue
                comp_cat = next(
                    (c for c in b.get("category_discounts", [])
                     if c.get("category", "").strip() == cat),
                    None,
                )
                if not comp_cat:
                    continue
                comp_pct = comp_cat.get("max_discount_pct", 0)
                if comp_pct - our_pct >= 10:
                    loser_rows.append({
                        "category": cat,
                        "competitor": b["name"],
                        "comp_pct": comp_pct,
                        "our_pct": our_pct,
                        "gap": comp_pct - our_pct,
                    })
    loser_rows.sort(key=lambda x: x["gap"], reverse=True)
    loser_rows = loser_rows[:5]

    # Build winners HTML
    winner_cards = []
    for deal in top_deals:
        label = "⭐ " if deal["is_ours"] else ""
        winner_cards.append(f"""
        <div class="gap-card" style="border-left-color:#27AE60;">
          <div class="gap-num" style="color:#27AE60;">{label}{_e(deal["brand"])} — {_e(deal["category"])}</div>
          <p style="font-size:13px;font-weight:700;color:#27AE60;">{deal["discount_pct"]}% off</p>
          <p>{_e(deal.get("product_name",""))}<br>
          <span style="font-size:11px;color:#888;">${deal["original_price"]:.2f} → ${deal["sale_price"]:.2f}</span></p>
        </div>""")

    # Build losers HTML
    loser_cards = []
    for row in loser_rows:
        loser_cards.append(f"""
        <div class="gap-card">
          <div class="gap-num">{_e(our_name)} vs {_e(row["competitor"])} — {_e(row["category"])}</div>
          <p><strong>{_e(our_name)}:</strong> {row["our_pct"]}% max off<br>
          <strong>{_e(row["competitor"])}:</strong> {row["comp_pct"]}% max off<br>
          <span style="color:#C62828;font-weight:600;">Gap: {row["gap"]} percentage points</span></p>
        </div>""")

    winners_html = (
        '<div class="gap-grid">' + "".join(winner_cards) + "</div>"
        if winner_cards else
        '<p style="color:#888;font-size:13px;">No top deal examples found.</p>'
    )
    losers_html = (
        '<div class="gap-grid">' + "".join(loser_cards) + "</div>"
        if loser_cards else
        f'<p style="color:#27AE60;font-size:13px;">No significant discount gaps found — {_e(our_name)} is competitive!</p>'
    )

    return f"""
    <h3 style="font-size:13px;font-weight:700;color:#27AE60;margin-bottom:10px;">
      🏆 Biggest Deals (Best Discounts for Shoppers)
    </h3>
    {winners_html}
    <h3 style="font-size:13px;font-weight:700;color:#E74C3C;margin-top:20px;margin-bottom:10px;">
      ⚠️ Where {_e(our_name)} Falls Behind
    </h3>
    {losers_html}"""


def _rec_list(recs: list[str]) -> str:
    if not recs:
        return ""
    items = []
    for i, r in enumerate(recs, 1):
        items.append(f"""
        <li>
          <span class="rec-num">{i}</span>
          <span class="rec-text">{_e(r)}</span>
        </li>""")
    return '<ul class="rec-list">' + "".join(items) + "</ul>"


# ── Main entry point ───────────────────────────────────────────────────────────

CSS = """
:root{--primary:#1B3A6B;--accent:#E8365D;--bg:#EEF2F7;--card:#fff;
  --text:#2C3E50;--muted:#7F8C8D;--border:#D9E2EF;--r:10px;
  --shadow:0 2px 14px rgba(0,0,0,.07);}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;}
a{color:var(--primary);}

/* Header */
header{background:linear-gradient(135deg,#1B3A6B 0%,#2A5298 100%);
  color:#fff;padding:26px 40px;display:flex;align-items:flex-start;justify-content:space-between;}
header h1{font-size:22px;font-weight:800;letter-spacing:-.5px;}
header .sub{font-size:13px;opacity:.7;margin-top:5px;}
.header-meta{text-align:right;font-size:12px;opacity:.6;}

/* Layout */
.container{max-width:1500px;margin:0 auto;padding:28px 32px;}
.section{margin-bottom:36px;}
h2{font-size:15px;font-weight:700;color:var(--primary);margin-bottom:14px;
   border-left:4px solid var(--accent);padding-left:10px;}

/* Summary box */
.summary{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);
  padding:18px 22px;border-left:4px solid var(--primary);font-size:13px;
  line-height:1.7;color:var(--text);}

/* Brand cards */
.brand-cards{display:flex;gap:12px;flex-wrap:wrap;}
.brand-card{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);
  padding:16px 20px;flex:1;min-width:160px;}
.bc-name{font-weight:700;font-size:13px;}
.bc-url{font-size:11px;color:var(--muted);margin-top:2px;}
.bc-row{display:flex;gap:20px;margin-top:12px;}
.bc-big{font-size:26px;font-weight:800;color:var(--primary);}
.bc-lbl{font-size:10px;color:var(--muted);}

/* Matrix */
.matrix-wrap{overflow-x:auto;}
.matrix{width:100%;border-collapse:collapse;background:var(--card);
  border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden;}
.matrix th{background:var(--primary);color:#fff;padding:11px 14px;
  font-size:12px;font-weight:600;text-align:center;white-space:nowrap;}
.matrix th.corner{background:#1a2e50;text-align:left;min-width:130px;}
.matrix th.ours-col{background:var(--accent);}
.matrix td{padding:10px 12px;text-align:center;vertical-align:top;
  border-bottom:1px solid #F2F2F2;cursor:default;transition:filter .1s;}
.matrix td:hover{filter:brightness(.93);}
.matrix tr:last-child td{border-bottom:none;}
.matrix td.cat-label{background:#FAFBFC;font-weight:600;font-size:12px;
  text-align:left;border-right:2px solid var(--border);}
.dp{display:block;font-size:20px;font-weight:800;}
.dd{display:block;font-size:10px;opacity:.75;margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;}

/* Legend */
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;padding:4px 0;}
.leg-item{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);}
.leg-dot{width:14px;height:14px;border-radius:3px;flex-shrink:0;}

/* Row table (site-wide offers) */
.rt{width:100%;border-collapse:collapse;background:var(--card);
  border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden;}
.rt th{background:var(--primary);color:#fff;padding:10px 14px;
  font-size:12px;font-weight:600;text-align:left;}
.rt th.ours-col{background:var(--accent);}
.rt td{padding:10px 14px;border-bottom:1px solid #F2F2F2;font-size:12px;vertical-align:top;}
.rt tr:last-child td{border-bottom:none;}
.rt td.rt-label,.rt td.rt-type{font-weight:600;background:#FAFBFC;
  border-right:2px solid var(--border);white-space:nowrap;color:var(--text);}
.check{color:#27AE60;font-weight:700;}
.cross{color:#CCC;}

/* Gap cards */
.gap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;}
.gap-card{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);
  padding:16px;border-left:4px solid #E74C3C;}
.gap-num{font-weight:700;font-size:11px;color:#E74C3C;margin-bottom:6px;
  text-transform:uppercase;letter-spacing:.5px;}
.gap-card p{font-size:12px;line-height:1.6;}

/* Recommendations */
.rec-list{list-style:none;display:flex;flex-direction:column;gap:10px;}
.rec-list li{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);
  padding:14px 18px;display:flex;gap:14px;align-items:flex-start;}
.rec-num{background:var(--primary);color:#fff;border-radius:50%;width:26px;
  height:26px;flex-shrink:0;display:flex;align-items:center;justify-content:center;
  font-size:12px;font-weight:700;}
.rec-text{font-size:13px;line-height:1.6;}

@media(max-width:700px){
  header{flex-direction:column;gap:8px;}
  .container{padding:16px;}
  .brand-cards{flex-direction:column;}
}
"""


def generate_html(data: dict) -> str:
    brands: list[dict] = data.get("brands", [])
    summary: str = data.get("analysis_summary", "")
    gaps: list[str] = data.get("gaps", [])
    recommendations: list[str] = data.get("recommendations", [])
    date_str = datetime.now().strftime("%B %d, %Y  %H:%M")

    our_brand = next((b for b in brands if b.get("is_ours")), None)
    our_name = our_brand["name"] if our_brand else "Our Brand"

    # Collect ordered category list (ours first, then union of all)
    all_cats: list[str] = []
    priority = ["Men's", "Women's", "Kids", "Boys", "Girls",
                "Accessories", "Footwear", "Home & Gifts", "Sale / Clearance"]
    for cat in priority:
        for b in brands:
            for c in b.get("category_discounts", []):
                if c["category"].strip() == cat and cat not in all_cats:
                    all_cats.append(cat)
    # Append any remaining categories not in the priority list
    for b in brands:
        for c in b.get("category_discounts", []):
            n = c["category"].strip()
            if n not in all_cats:
                all_cats.append(n)

    body = f"""
    <div class="section">
      <h2>Executive Summary</h2>
      <div class="summary">{_e(summary)}</div>
    </div>

    <div class="section">
      <h2>Brand Overview</h2>
      {_brand_cards(brands)}
    </div>

    <div class="section">
      <h2>Discount by Category — Competitive Matrix</h2>
      {_category_matrix(brands, all_cats)}
    </div>

    <div class="section">
      <h2>Site-Wide &amp; Promotional Offers</h2>
      {_sitewide_table(brands)}
    </div>

    <div class="section">
      <h2>Price Intelligence — Before &amp; After Discounts</h2>
      {_price_intelligence_table(brands, all_cats)}
    </div>

    <div class="section">
      <h2>Biggest Deals &amp; Biggest Losers</h2>
      {_winners_losers_cards(brands, our_name)}
    </div>

    <div class="section">
      <h2>Gap Analysis — Where {_e(our_name)} Could Improve</h2>
      {_gap_cards(gaps)}
    </div>

    <div class="section">
      <h2>Recommendations</h2>
      {_rec_list(recommendations)}
    </div>
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(our_name)} — Discount Intelligence Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div>
    <h1>🐳 {_e(our_name)} — Discount Intelligence</h1>
    <div class="sub">Competitive discount &amp; promotion analysis across categories</div>
  </div>
  <div class="header-meta">Generated<br>{_e(date_str)}</div>
</header>
<div class="container">
{body}
</div>
</body>
</html>"""
