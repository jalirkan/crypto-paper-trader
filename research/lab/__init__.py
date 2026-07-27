"""The AI Research Lab — autonomous strategy discovery with statistical honesty.

Pipeline:
  generate (Claude or random) → validate (DSL) → evaluate (search span only)
  → rank with robustness penalty → next generation → … → FINALIZE:
  top-M face a SEALED holdout exactly once, judged by deflated Sharpe
  (corrected for every candidate ever tried) and stationary-bootstrap p-values.

The design premise: automated search is an overfitting machine unless every
trial is counted against the final result. The lab counts them.
"""
