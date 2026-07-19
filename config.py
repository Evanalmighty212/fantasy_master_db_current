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

# Component 1 (ADP Value): if a player's overall finish was WORSE than
# their own overall ADP, their Component 1 score is capped at this
# value (out of 100) regardless of how favorably they scored against
# the historical expected-finish baseline (EVA). Verified via real-data
# testing: without this cap, EVA alone could score a player positively
# for beating a bad historical baseline (early picks bust often) even
# when they genuinely underperformed the actual pick spent on them --
# real case: Arian Foster 2012 (drafted 1.4 overall, finished 12th).
# 40 is comfortably below the 50-midpoint "met expectation" range,
# ensuring a real underperformer cannot reach the top of the LWI
# leaderboard through this component alone.
LWI_ADP_UNDERPERFORM_CAP = 40

# --- Undrafted player representation (verified-undrafted proxy ADP) ---
# Product decision: a metric called "League Winner Index" must be able
# to recognize genuinely undrafted breakout players (James Robinson
# 2020, Victor Cruz 2011, etc.) -- excluding them entirely would make
# the metric measure something narrower than its own name implies.
# ONE unified acquisition model, not a separate scoring path: a
# verified-undrafted player gets a MODELED overall/positional ADP
# (see 04_build_master_dataset.py's apply_undrafted_proxy_adp) and
# then flows through the exact same Component 1-6 pipeline as every
# drafted player.
#
# Proxy formula: GLOBAL maximum observed ADP (across all 2006-2025
# seasons combined) + 1 -- NOT each season's own deepest pick + 1.
# Rationale: a player taken with the literal last pick of a draft and
# one who goes undrafted are usually separated by one manager's
# last-round decision, not a fundamentally different acquisition
# mechanism -- the proxy should reflect that continuity. Using each
# season's OWN source depth instead would unfairly reward players from
# seasons where the ADP source happened to be shallower (e.g. 2022's
# 146-player depth vs 2010's 214), which is a property of the SOURCE,
# not the player's real draft standing.
#
# THESE ARE FIXED CONSTANTS, not dynamically recomputed each pipeline
# run. If they were recalculated automatically whenever new ADP data
# is added, every previously-scored undrafted player's modeled ADP
# would silently shift, breaking reproducibility across output
# versions. Computed once from the real 2006-2025 dataset (verified
# directly): global max overall_adp = 193.5 (so proxy = 194.5); global
# max positional_adp by position from the matched master dataset:
# QB=30 (proxy=31), RB=64 (proxy=65), WR=73 (proxy=74), TE=60 (proxy=61).
# Revisit deliberately (not automatically) if a future season's real
# ADP data ever exceeds these depths.
LWI_GLOBAL_MAX_OVERALL_ADP = 193.5
LWI_GLOBAL_MAX_POSITIONAL_ADP = {"QB": 30, "RB": 64, "WR": 73, "TE": 60}

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
#
# v2.0: major formula redesign after extensive real-data testing --
# Component 1 changed from positional/overall ADP comparison to
# leave-one-season-out (LOSO) monotonic EVA + an overall-ADP-
# underperformance cap; Component 2 changed to total points above
# replacement (cross-position); Component 3 reverted to positional PPG
# percentile (found to be mathematically identical to Component 4 when
# also made replacement-adjusted). See docs/METRIC_SPECIFICATION.md
# for the full history of this redesign.
# v2.1: Component 4 redesigned to STANDARDIZED positional advantage
# (PPG above replacement / IQR of starter-tier PPG at that position)
# after finding v2.0's Component 4 was mathematically identical to
# Component 3 once Component 3 was also made replacement-adjusted
# (both were literally the same formula, weighted twice). An
# intermediate fallback (reverting Component 3 to positional
# percentile) fixed the duplication but reintroduced TE over-
# representation (15% of a real top-100, vs 5% for the original,
# fully-redundant version). Standardizing Component 4 by the
# position's own scoring spread instead resolved BOTH problems:
# 25% unique variance (vs 0% when unstandardized) and 7% TE share
# (vs 5-16% for every other variant tested). Component 3 restored to
# replacement-adjusted since it no longer duplicates the redesigned
# Component 4. See docs/METRIC_SPECIFICATION.md for the full history.
# v2.1: FINAL. Confirmed via release verification -- production output
# reproduces the tested winsor-5/95 formula almost exactly (false-
# positive median 596 exact match, unique variance 15.46% vs tested
# 15.5%, Component3-4 correlation 0.942 vs tested 0.942). Fixed a real
# outlier-sensitivity bug in Component 4's final normalization along
# the way (rc2): plain min-max (used through v2.1-rc1) is highly
# sensitive to its own extremes -- verified directly that a single
# wild outlier in ONE position's data could shift an UNRELATED
# player's score in a DIFFERENT position by 60+ points, since the
# final cross-position normalization shares one range across all 4
# positions within a season. Fixed by winsorizing (5th/95th percentile
# clip) before scaling -- tested head-to-head against plain min-max,
# percentile rank, and 2.5/97.5 winsorizing; 5/95 gave the best
# combination of outlier robustness (0.0 point shift in the same test
# that showed 60+ before) and retained discriminative power. See
# docs/METRIC_SPECIFICATION.md Component 4 and docs/LWI_MODEL_CARD.md
# for full details.
LWI_VERSION = "2.1"


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

    if not isinstance(LWI_ADP_UNDERPERFORM_CAP, (int, float)) or not (0 <= LWI_ADP_UNDERPERFORM_CAP <= 100):
        errors.append(f"LWI_ADP_UNDERPERFORM_CAP must be a number in [0, 100], "
                       f"got {LWI_ADP_UNDERPERFORM_CAP}")

    if not isinstance(LWI_GLOBAL_MAX_OVERALL_ADP, (int, float)) or LWI_GLOBAL_MAX_OVERALL_ADP <= 0:
        errors.append(f"LWI_GLOBAL_MAX_OVERALL_ADP must be a positive number, "
                       f"got {LWI_GLOBAL_MAX_OVERALL_ADP}")
    for pos, val in LWI_GLOBAL_MAX_POSITIONAL_ADP.items():
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"LWI_GLOBAL_MAX_POSITIONAL_ADP['{pos}'] must be a "
                           f"positive number, got {val}")

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
