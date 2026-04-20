"""
Configuration for the competitor discount agent.

OUR_SITE is Vineyard Vines. COMPETITOR_SITES covers direct competitors
in the preppy / lifestyle / outdoor apparel space.
"""

OUR_SITE = {
    "name": "Vineyard Vines",
    "base_url": "https://www.vineyardvines.com",
}

COMPETITOR_SITES = [
    # ── Explicitly requested ──────────────────────────────────────────
    {
        "name": "J.Crew",
        "base_url": "https://www.jcrew.com",
    },
    {
        "name": "Lululemon",
        "base_url": "https://www.lululemon.com",
    },
    {
        "name": "Bird Dog",
        "base_url": "https://birddogpants.com",
    },
    # ── Close preppy / lifestyle competitors ─────────────────────────
    {
        "name": "Ralph Lauren",
        "base_url": "https://www.ralphlauren.com",
    },
    {
        "name": "Tommy Hilfiger",
        "base_url": "https://www.tommyhilfiger.com",
    },
    {
        "name": "Southern Tide",
        "base_url": "https://www.southerntide.com",
    },
    {
        "name": "Chubbies",
        "base_url": "https://www.chubbiesshorts.com",
    },
    {
        "name": "Faherty Brand",
        "base_url": "https://fahertybrand.com",
    },
    {
        "name": "Peter Millar",
        "base_url": "https://www.petermillar.com",
    },
    {
        "name": "Brooks Brothers",
        "base_url": "https://www.brooksbrothers.com",
    },
]

# Keywords that signal discount / promotional content
DISCOUNT_KEYWORDS = [
    "discount", "deal", "promo", "promotion", "offer", "save", "sale",
    "% off", "coupon", "voucher", "gift card", "special", "limited",
    "bundle", "subscribe", "subscription", "referral", "first order",
    "new customer", "welcome", "extra", "clearance", "final sale",
    "flash sale", "sitewide", "code", "reward", "loyalty", "member",
]
