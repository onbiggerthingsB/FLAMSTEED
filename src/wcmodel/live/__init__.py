"""Phase-5 live forward-test package: thin live wrappers over the merged Phase 1-4
per-cutoff machinery (the backtest body at ``cutoff = now``). SIGNAL-ONLY / PAPER:
no order/broker/exchange path; no real odds spend until the feed is funded (L1/L2).
"""
