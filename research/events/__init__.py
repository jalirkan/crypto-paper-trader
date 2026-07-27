"""LLM event pipeline: classify news → event studies → (maybe) signals.

Shared label schema. Labels live in the archive DB next to the news table.
"""

LABELS_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_labels (
  news_id    TEXT PRIMARY KEY,
  model      TEXT NOT NULL,
  labeled_ts INTEGER NOT NULL,
  relevant   INTEGER NOT NULL,          -- 0/1: market-moving crypto news at all?
  event_type TEXT NOT NULL,             -- regulation | etf_flows | hack_exploit |
                                        -- exchange | macro | adoption | tech | legal | other
  assets     TEXT NOT NULL,             -- CSV of symbols, or MARKET
  direction  INTEGER NOT NULL,          -- -1 bearish / 0 neutral / +1 bullish
  magnitude  INTEGER NOT NULL,          -- 1 minor / 2 notable / 3 major
  novelty    INTEGER NOT NULL,          -- 1 = first report, 0 = follow-up/rehash
  confidence TEXT NOT NULL,             -- low | medium | high
  raw_json   TEXT
);
"""

EVENT_TYPES = [
    "regulation",
    "etf_flows",
    "hack_exploit",
    "exchange",
    "macro",
    "adoption",
    "tech",
    "legal",
    "other",
]
