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
# rationale behind each of these. Anything marked "not yet formally
# confirmed" in that document is a real open decision, not a
# throwaway default -- change it here if/when it gets confirmed.

# The core formula weights (46/18/17/12/4/3), from VERSION_1_SCOPE.md.
LWI_WEIGHTS = {
    "adp_value": 0.46,
    "fantasy_finish": 0.18,
    "ppg": 0.17,
    "positional_advantage": 0.12,
    "playoff_performance": 0.04,
    "consistency": 0.03,
}

# Minimum games played for a player-season to be eligible for an LWI
# score at all (see METRIC_SPECIFICATION.md "Scope" section).
LWI_MIN_GAMES = 8

# data_quality_flag values (from 04_build_master_dataset.py) that
# qualify a row for LWI scoring -- a row needs a real ADP match to
# have a "value over draft cost" score at all.
LWI_ELIGIBLE_QUALITY_FLAGS = {"matched_clean", "matched_needs_review"}

# Component 4 (Positional Advantage): replacement-level rank threshold
# per position, and the window width above it to median over.
#
# CONFIRMED (was: proposed default) -- QB12/RB34/WR42/TE12. This is a
# CONCEPTUAL choice, not an empirical finding: real historical scoring
# curves show NO natural cliff at any candidate threshold (QB/RB/WR/TE
# all decay smoothly after the elite tier, with no second discontinuity
# marking "starter" vs "waiver"), so no threshold set can be called
# empirically "correct." QB12/RB34/WR42/TE12 was chosen because it best
# matches the spec's own definition of replacement level -- "freely
# available," not merely "the last mandatory starter" -- while avoiding
# false precision at either extreme (RB30/WR36 undersells how deep
# fantasy managers actually hoard those positions; RB36/WR48
# overshoots into bench-only territory).
#
# Sensitivity-tested against real 2006-2024 data before confirming:
# rank correlation of 0.9996 between the most divergent candidate
# configurations tested, top-25 set overlap 23/25, top-100 set overlap
# 97/100, median rank movement across all 2,643 eligible rows of 8
# (95th percentile: 49). Per-season #1 changed in 2 of 18 seasons
# under the most extreme comparison, but both were already
# razor-margin races (0.02 and ~0.1 points on a 100-point scale) that
# could plausibly tip either way from minor input changes -- not cases
# of a clear #1 being meaningfully displaced.
LWI_REPLACEMENT_RANK_THRESHOLDS = {"QB": 12, "RB": 34, "WR": 42, "TE": 12}
LWI_REPLACEMENT_WINDOW = 12

# Component 5 (Playoff Performance): which weeks count as "playoffs,"
# split by NFL season length era. Verified against actual
# max-week-per-season in the real data -- see METRIC_SPECIFICATION.md
# Component 5 for the full rationale. LWI_PLAYOFF_ERA_CUTOFF_SEASON is
# the last season using the shorter (16-game) week set; anything after
# it uses the 17-game week set.
LWI_PLAYOFF_WEEKS_16_GAME_ERA = [14, 15, 16]
LWI_PLAYOFF_WEEKS_17_GAME_ERA = [15, 16, 17]
LWI_PLAYOFF_ERA_CUTOFF_SEASON = 2020

# Version identifier for the LWI formula itself. Bump this any time any
# LWI_* value above changes -- "LWI 82.4" means something different
# under a different config, and output files should always be able to
# say which formula version produced them (see calculate_lwi()'s
# lwi_version / lwi_config_fingerprint output columns).
LWI_VERSION = "1.0"


def validate_lwi_config():
    """
    Fail loudly on an invalid LWI configuration rather than silently
    calculating plausible-looking scores from bad inputs. Called at
    the start of 05_calculate_metrics.py -- not optional, not a
    warning. A centralized config file also centralizes the
    opportunity for someone to enter a bad value; this is the guard
    against that.
    """
    errors = []

    weight_sum = sum(LWI_WEIGHTS.values())
    if abs(weight_sum - 1.0) > 1e-6:
        errors.append(f"LWI_WEIGHTS must sum to 1.0 (100%), got {weight_sum}")
    for name, w in LWI_WEIGHTS.items():
        if w < 0:
            errors.append(f"LWI_WEIGHTS['{name}'] is negative ({w})")

    if not isinstance(LWI_MIN_GAMES, int) or not (1 <= LWI_MIN_GAMES <= 17):
        errors.append(f"LWI_MIN_GAMES must be an integer in [1, 17], got {LWI_MIN_GAMES}")

    for pos, threshold in LWI_REPLACEMENT_RANK_THRESHOLDS.items():
        if not isinstance(threshold, int) or threshold <= 0:
            errors.append(f"LWI_REPLACEMENT_RANK_THRESHOLDS['{pos}'] must be a "
                           f"positive integer, got {threshold}")
    if not isinstance(LWI_REPLACEMENT_WINDOW, int) or LWI_REPLACEMENT_WINDOW <= 0:
        errors.append(f"LWI_REPLACEMENT_WINDOW must be a positive integer, "
                       f"got {LWI_REPLACEMENT_WINDOW}")

    for era_name, weeks in [("LWI_PLAYOFF_WEEKS_16_GAME_ERA", LWI_PLAYOFF_WEEKS_16_GAME_ERA),
                             ("LWI_PLAYOFF_WEEKS_17_GAME_ERA", LWI_PLAYOFF_WEEKS_17_GAME_ERA)]:
        if not weeks or any((not isinstance(w, int) or w < 1 or w > 22) for w in weeks):
            errors.append(f"{era_name} must be a non-empty list of valid week "
                           f"numbers (1-22), got {weeks}")
    if not isinstance(LWI_PLAYOFF_ERA_CUTOFF_SEASON, int):
        errors.append(f"LWI_PLAYOFF_ERA_CUTOFF_SEASON must be an integer season, "
                       f"got {LWI_PLAYOFF_ERA_CUTOFF_SEASON}")

    if errors:
        raise ValueError(
            "Invalid LWI configuration in config.py:\n  - " + "\n  - ".join(errors)
        )
