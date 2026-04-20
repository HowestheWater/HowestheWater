"""
Configuration for the competitor discount agent.

Update OUR_SITE with HowestheWater's actual URL.
Add competitor sites to COMPETITOR_SITES.
"""

OUR_SITE = {
    "name": "HowestheWater",
    "base_url": "https://howesthewater.com",
}

COMPETITOR_SITES = [
    {
        "name": "ReadyRefresh",
        "base_url": "https://www.readyrefresh.com",
    },
    {
        "name": "Primo Water",
        "base_url": "https://www.primowater.com",
    },
    {
        "name": "DS Waters",
        "base_url": "https://www.dswateronline.com",
    },
]

# Keywords that signal discount/promotional content
DISCOUNT_KEYWORDS = [
    "discount", "deal", "promo", "promotion", "offer", "save", "sale",
    "% off", "coupon", "voucher", "free", "trial", "special", "limited",
    "bundle", "subscribe", "subscription", "referral", "first month",
    "introductory", "new customer",
]
