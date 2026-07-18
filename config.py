"""
config.py

Central location for tunable parameters used across the pipeline.
Per project convention: anything that represents a real judgment call
or could reasonably need adjusting later lives here, not embedded
inside a script's formula logic. If you're changing a NUMBER that
affects what the pipeline calculates (not how it calculates it),
change it here.
"""

SEASONS = list(range(2006, 2026))
SCORING_FORMATS = ["ppr"]
TEAMS = 12
TOP_N_ADP = 250

# --- League Winner Index (LWI) parameters ---
# See docs/METRIC_SPECIFICATION.md for the full formula writeup and
# rationale
