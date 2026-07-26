"""Tracked assets and data source configuration.

Zero external dependencies by design — the collector layer runs on a bare
Python 3.10+ install (Windows, VPS, anywhere).
"""

# Symbol map across venues. `coinbase: None` = not listed there.
COINS = [
    {"sym": "BTC", "coingecko": "bitcoin", "binance": "BTCUSDT", "coinbase": "BTC-USD"},
    {"sym": "ETH", "coingecko": "ethereum", "binance": "ETHUSDT", "coinbase": "ETH-USD"},
    {"sym": "SOL", "coingecko": "solana", "binance": "SOLUSDT", "coinbase": "SOL-USD"},
    {"sym": "BNB", "coingecko": "binancecoin", "binance": "BNBUSDT", "coinbase": None},
    {"sym": "XRP", "coingecko": "ripple", "binance": "XRPUSDT", "coinbase": "XRP-USD"},
    {"sym": "ADA", "coingecko": "cardano", "binance": "ADAUSDT", "coinbase": "ADA-USD"},
    {"sym": "DOGE", "coingecko": "dogecoin", "binance": "DOGEUSDT", "coinbase": "DOGE-USD"},
    {"sym": "AVAX", "coingecko": "avalanche-2", "binance": "AVAXUSDT", "coinbase": "AVAX-USD"},
    {"sym": "LINK", "coingecko": "chainlink", "binance": "LINKUSDT", "coinbase": "LINK-USD"},
    {"sym": "LTC", "coingecko": "litecoin", "binance": "LTCUSDT", "coinbase": "LTC-USD"},
]

# Perp funding tracked for the majors only (delta-neutral sleeve candidates).
FUNDING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# News feeds — no API keys required. (CryptoPanic/Reddit/Alpaca can be added
# later behind env keys; see research/README.md.)
RSS_FEEDS = [
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("theblock", "https://www.theblock.co/rss.xml"),
    ("decrypt", "https://decrypt.co/feed"),
]

# Backfill depth
DAILY_BACKFILL_DAYS = 3 * 365
HOURLY_BACKFILL_DAYS = 365

USER_AGENT = "crypto-paper-trader-collector/0.1 (personal research project)"
