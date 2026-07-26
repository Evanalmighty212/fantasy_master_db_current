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


# =====================================================================
# --- Stars-by-Value (SBV) parameters -- Dataset 3 historical label ---
# =====================================================================
# See research/dataset3/STARS_BY_VALUE_METHODOLOGY.md for the full
# settled decision record (sections 1-11) and
# research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md for how this
# turns into pipeline code. Kept FULLY SEPARATE from the LWI_* block
# above on purpose -- Stars-by-Value (Dataset 3) and LWI (Dataset 1)
# are two different specs, with their own, independently-calibrated
# replacement-level definitions and formulas. Never read an LWI_*
# constant from SBV code, or vice versa, even where a name or shape
# coincidentally matches (see TestNoAccidentalLwiReuse in
# tests/test_sbv_config.py).
#
# Every constant below is tagged [SETTLED METHODOLOGY] (a real,
# empirically-calibrated decision recorded in
# STARS_BY_VALUE_METHODOLOGY.md -- change it there first, this file
# second) or [IMPLEMENTATION METADATA] (a name, path, or grouping
# that supports the settled methodology but isn't itself a
# methodological decision).

# [IMPLEMENTATION METADATA] Version identifier for the SBV formula/
# schema as a whole -- bump whenever any SBV_* value below changes in
# a way that would make output non-comparable to a prior run,
# mirroring LWI_VERSION's convention. Also the value stamped into
# every row of the expected-production lookup cache
# (SBV_EXPECTED_PRODUCTION_LOOKUP_PATH) so a stale cache can be
# detected and rejected rather than silently used.
SBV_VERSION = "1.0"

# [IMPLEMENTATION METADATA] The four positions Stars-by-Value applies
# to. A player-season at any other position is always out_of_scope
# (provenance out_of_scope_non_skill_position) -- see SBV_STATUSES.
SBV_POSITIONS = ("QB", "RB", "WR", "TE")

# [SETTLED METHODOLOGY] Section 7 -- honest expanding-window fitting:
# minimum prior seasons required before any E_P prediction is made,
# and the season trustworthy ADP data begins. SBV_FIRST_SCOREABLE_SEASON
# is DERIVED from the other two (2007 + 3 = 2010), not an
# independently chosen cutoff -- validate_sbv_config() checks this
# arithmetic directly rather than letting the three drift apart.
SBV_TRUSTWORTHY_ADP_START_SEASON = 2007
SBV_MIN_PRIOR_SEASONS = 3
SBV_FIRST_SCOREABLE_SEASON = 2010

# [SETTLED METHODOLOGY] Section 2 -- verified historical regular-season
# length, NOT derived from max(games_played) in the data (two known
# single-row anomalies traced to mid-season team changes, not real
# 17/18-game seasons -- see section 2). SBV_SEASON_LENGTH_ERA_CUTOFF is
# the first season using the 17-game length; every season before it
# uses 16.
SBV_SEASON_LENGTH_16_GAME = 16
SBV_SEASON_LENGTH_17_GAME = 17
SBV_SEASON_LENGTH_ERA_CUTOFF = 2021

# [SETTLED METHODOLOGY] Section 3 -- normalized reliability shrinkage.
# A continuous confidence parameter, not a minimum-games cutoff -- it
# reaches exactly 1.0 (full trust) only at a complete season. See
# section 3 for why k=5 was chosen over k=2/4/6/7/8.
SBV_SHRINKAGE_K = 5

# [SETTLED METHODOLOGY] Section 4 -- production composite weights.
# Provisional 50/50 per section 4's own text -- alternative splits
# were tested and found statistically indistinguishable, but the
# weight choice itself is explicitly left open pending further
# calibration, unlike the other constants in this block. Recorded
# here because it's the value actually in use, not because it's
# beyond revisiting.
SBV_PRODUCTION_WEIGHT_AATP = 0.5
SBV_PRODUCTION_WEIGHT_PPG_EQ = 0.5

# [SETTLED METHODOLOGY] Section 5 -- meaningful-production gate
# (p82.5): fixed, position-specific production-composite floors,
# calibrated once from the full historical reference population and
# held constant across seasons (the Absolute Impact property applied
# to the gate itself).
SBV_PRODUCTION_GATE_FLOOR = {
    "QB": 142.599891,
    "RB": 113.712500,
    "WR": 98.105667,
    "TE": 66.679583,
}

# [SETTLED METHODOLOGY] Section 5 -- the replacement-level definition
# SBV uses (flex_rb_wr_heavy). DISTINCT from LWI_REPLACEMENT_RANK_THRESHOLDS
# above -- do not conflate the two specs' replacement definitions,
# even though both ultimately compute "replacement level" from roster
# math. The rank cutoffs and flex split differ from LWI's on purpose
# (independently calibrated, not a shared value).
SBV_REPLACEMENT_ROSTER_PRESET = "12_team_standard"
SBV_REPLACEMENT_RANK_CUTOFFS = {"QB": 12, "RB": 29, "WR": 29, "TE": 13}
SBV_REPLACEMENT_FLEX_ALLOCATION = {"RB": 0.45, "WR": 0.45, "TE": 0.10}
SBV_REPLACEMENT_WINDOW = 12

# [SETTLED METHODOLOGY] Section 7 -- expected-production-by-round
# fitting. QB_RB is the settled positional-offset variant (statistically
# indistinguishable from the full four-position ceiling, while TE-only/
# WR-only barely beat doing nothing). Recency weighting (5-year half-
# life) is QB-SPECIFIC -- reconfirmed significant for QB only, not RB
# or WR, under the fully settled construction.
SBV_ROUND_OFFSET_POSITIONS = frozenset({"QB", "RB"})
SBV_RECENCY_HALF_LIFE_YEARS = 5
SBV_RECENCY_POSITIONS = frozenset({"QB"})

# [SETTLED METHODOLOGY] Section 10 -- lambda (the weight on the
# acquisition-cost penalty in Stars-by-Value Score = P - lambda x E_P)
# and the final, settled position-specific Star thresholds. Both are
# calibration choices supported by face validity, sensitivity
# analysis, and narrative-blind review -- explicitly NOT discovered
# natural breakpoints (section 10's "Gap analysis" found no dominant
# natural break inside the plausible region for any position).
SBV_LAMBDA = 0.35
SBV_STAR_THRESHOLD = {"QB": 176.5, "RB": 188, "WR": 171, "TE": 134}

# [SETTLED METHODOLOGY] Section 9 -- minimal-market-cost expectation:
# MMC_E_P(position, season) = opportunity_probability(position) x 0.5
# x replacement_ppg(position) x G(season). Both the probabilities and
# the replacement rates below are FROZEN, already-calibrated outputs
# (equal-weighted full history 2007-2024; checked for era drift across
# four eras and found none large or monotonic enough to justify
# recency weighting) -- never recomputed live from a fresh
# stats_player/MFL fetch at scoring time. The published headline
# figures (31.0/23.1/35.7/19.3) are specifically the 17-game-era
# (G=2021+) values -- season-varying G is applied at scoring time in
# code, not baked into a single constant here.
SBV_MMC_OPPORTUNITY_PROBABILITY = {"QB": 0.247, "RB": 0.290, "WR": 0.368, "TE": 0.285}
SBV_MMC_REPLACEMENT_PPG = {"QB": 14.746, "RB": 9.361, "WR": 11.423, "TE": 7.970}

# [SETTLED METHODOLOGY] Section 9 -- the role-conditional production
# discount in the MMC_E_P formula above: "if this player gets real
# opportunity, they'd produce at roughly half replacement-level rate."
# A DEDICATED constant, deliberately NOT the same as
# SBV_PRODUCTION_WEIGHT_AATP -- the two currently share a value (0.5)
# but are different quantities (this is a production-rate discount
# conditional on getting opportunity; SBV_PRODUCTION_WEIGHT_AATP is the
# AATP/PPG_AR_eq_shrunk composite weight in production.py). Reusing one
# constant for both was considered and rejected: they must be free to
# move independently if either is ever recalibrated.
SBV_MMC_ROLE_CONDITIONAL_DISCOUNT = 0.5

# [SETTLED METHODOLOGY] Section 9 -- the "meaningful usage" definition
# used ONLY to calibrate SBV_MMC_OPPORTUNITY_PROBABILITY above (a real,
# usage-based opportunity-rate estimate from a broad pre-outcome
# population, deliberately never fantasy points or the p82.5 gate).
# NOT consulted by scoring logic at runtime -- kept here for
# traceability if the probabilities are ever recalibrated. Explicitly
# documented in the methodology as "a convention, not a uniquely
# correct cutoff," which is exactly why it must stay a named config
# constant rather than an inline magic number.
SBV_MMC_USAGE_DEFINITION = {
    "QB": {"stat": "attempts", "min": 100},
    "RB": {"stat": "touches", "min": 40},
    "WR": {"stat": "targets", "min": 20},
    "TE": {"stat": "targets", "min": 20},
}

# [SETTLED METHODOLOGY] docs/ADP_SOURCE_MATRIX.md "No-ADP remediation"
# parts 3-4 -- the acquisition-cost classifier's rule-based thresholds.
# Hand-chosen heuristics, never themselves calibrated (explicitly
# disclosed as such in the settled record) -- disclosed as tunable
# judgment calls here, not embedded in acquisition_cost.py's logic.
SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK = 3
SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES = 4
SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS = 80.0
# NFL draft "Day 1-2" = rounds 1-3 (rounds 1, 2-3 on separate calendar
# days but grouped here per the classifier's own two-way split); "Day
# 3" = rounds 4-7. SBV_CLASSIFIER_DAY_1_2_MAX_ROUND is the boundary --
# draft_round <= this value is Day 1-2, anything higher (through 7) is
# Day 3.
SBV_CLASSIFIER_DAY_1_2_MAX_ROUND = 3

# [SETTLED METHODOLOGY] docs/ADP_SOURCE_MATRIX.md part 4's threshold
# sweep -- 20% is "the first threshold that groups all three low-signal
# named cases together" (Cruz 6.7%, Herbert 17.9%, Nacua 18.5%), used
# as a strict "<" boundary (the settled record only ever describes
# cases as "below" this value; no case sits exactly at 20.0%, so the
# boundary direction itself is an inference from that language, not a
# directly-tested edge case).
SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT = 20.0

# [IMPLEMENTATION METADATA] Section 9 -- MFL corroboration window and
# query period. MFL has no usable historical ADP data before 2011 at
# any query period (confirmed directly) -- the 2010 cohort uses the
# manual-override fallback (SBV_MMC_2010_OVERRIDE_PATH) instead.
# PERIOD must always be passed explicitly as AUG15 -- the
# unparameterized default MFL report blends in-season activity and is
# NOT a preseason snapshot (see docs/ADP_SOURCE_MATRIX.md's
# PERIOD-contamination finding).
SBV_MFL_AVAILABLE_FROM_SEASON = 2011
SBV_MFL_PERIOD = "AUG15"

# [IMPLEMENTATION METADATA] mfl_client.py rate-limiting/retry
# operational tunables. MFL's public API has no documented rate limit,
# but an earlier ad hoc parallel-batch attempt during the 2025 MFL
# investigation triggered what looked like transient rate-limiting/
# timeouts (see research/diagnostics/mfl_pipeline/mfl_client.py) --
# these values (serial requests, a minimum delay between real network
# calls, bounded retry with exponential backoff, a per-request
# timeout) exist to make hammering MFL's servers impossible by
# construction. Deliberately here rather than hardcoded in
# mfl_client.py: unlike nflverse's asset-ID pinning (a fixed protocol
# with no equivalent throttling need), these are real operational
# judgment calls that may legitimately need adjusting later --
# e.g. if MFL's tolerance changes -- without that being a methodology
# change.
SBV_MFL_MIN_REQUEST_DELAY_SECONDS = 1.5
SBV_MFL_MAX_RETRIES = 3
SBV_MFL_BACKOFF_BASE_SECONDS = 3
SBV_MFL_REQUEST_TIMEOUT_SECONDS = 20

# [SETTLED METHODOLOGY] Section 11 -- the seven mutually exclusive
# label statuses and the ten structured provenance values. Single
# source of truth: import these everywhere else that needs to
# validate or branch on status/provenance, rather than restating the
# list (and risking it drifting out of sync).
SBV_STATUSES = (
    "adp_scored",
    "unscoreable_adp_needs_review",
    "minimal_market_cost_scored",
    "unscoreable_drafted_adp_missing",
    "unscoreable_ambiguous",
    "below_production_gate",
    "out_of_scope",
)
SBV_PROVENANCE_TYPES = (
    "adp_matched_clean",
    "adp_matched_needs_review",
    "mmc_verified_corroborated",
    "mmc_verified_2010_manual_override",
    "evidence_drafted_unresolved",
    "evidence_ambiguous_disagreement",
    "below_production_gate",
    "out_of_scope_non_skill_position",
    "out_of_scope_temporal_window",
    "out_of_scope_insufficient_participation",
)

# [IMPLEMENTATION METADATA] Canonical artifact paths -- see the
# implementation plan's decisions #1 (separate Parquet output, not
# merged into the LWI master table), #2 (materialized E_P lookup
# cache), #3 (the 2010 manual-override file), and #5 (Parquet
# canonical, CSV a generated convenience export, never authoritative
# for dtype).
SBV_OUTPUT_PARQUET_PATH = "data/processed/stars_by_value_player_seasons.parquet"
SBV_OUTPUT_CSV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"
SBV_OUTPUT_CSV_SCHEMA_PATH = "data/exports/stars_by_value_player_seasons_SCHEMA.md"
SBV_EXPECTED_PRODUCTION_LOOKUP_PATH = "data/processed/sbv_expected_production_lookup.parquet"
SBV_MMC_2010_OVERRIDE_PATH = "data/manual/mmc_2010_manual_overrides.csv"

# [SETTLED METHODOLOGY] Section 11/8a -- which season(s) the manual-
# override mechanism is sanctioned for. Deliberately a SEPARATE
# constant from SBV_FIRST_SCOREABLE_SEASON: the two encode different
# concepts that only happen to share the value 2010 today --
# SBV_FIRST_SCOREABLE_SEASON is about temporal/study-scope eligibility
# (derived from SBV_TRUSTWORTHY_ADP_START_SEASON + SBV_MIN_PRIOR_SEASONS),
# while this is about which cohort(s) cannot be resolved by ADP
# matching OR MFL corroboration (MFL has zero data before 2011) and so
# need this fallback at all. Conflating them would make it look like
# extending the study's start season and extending the override
# mechanism were the same decision, when they are not -- either could
# change independently of the other, and each would be its own
# methodology decision (section 11), not just a config edit.
SBV_MMC_MANUAL_OVERRIDE_SEASONS = (2010,)

# [SETTLED METHODOLOGY] Section 8a rule #2 -- no 2010 override may be
# created from classifier output alone. Narrow and exact-match ON
# PURPOSE (revised after review): rejects a row only when 'source' IS,
# verbatim (case/whitespace/underscore-normalized), one of these
# literal internal-signal-name tokens -- e.g. someone pasting
# "classifier" or "draft_capital" as a lazy citation. Deliberately NOT
# a substring/phrase match against 'source' -- ordinary language in a
# genuine independent source ("cross-referenced against the team's own
# rookie status announcement") legitimately contains phrases like
# "rookie status" without restating the classifier's own reasoning,
# and a substring rule would reject that real source while being
# trivially evadable by rephrasing. This is a mechanical floor, not a
# substitute for human review at approval time -- see section 8a's own
# caveat that rule #2 is a process rule a loader can only partially
# enforce.
SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES = (
    "classifier",
    "internal_classifier_output",
    "acquisition_cost_classifier",
    "draft_capital",
    "rookie_status",
    "prior_production_heuristic",
)


def validate_sbv_config():
    """
    Fail loudly on an invalid SBV configuration rather than silently
    scoring/labeling from bad inputs -- mirrors validate_lwi_config()'s
    role and calling convention exactly. Intended to be called at the
    start of every SBV pipeline stage (08-11), not optional.
    """
    errors = []

    def _check_position_keys(name, d):
        if set(d.keys()) != set(SBV_POSITIONS):
            errors.append(
                f"{name} keys must be exactly {set(SBV_POSITIONS)}, got {set(d.keys())}"
            )

    # --- temporal derivation (not just asserted in a comment) ---
    if SBV_FIRST_SCOREABLE_SEASON != SBV_TRUSTWORTHY_ADP_START_SEASON + SBV_MIN_PRIOR_SEASONS:
        errors.append(
            "SBV_FIRST_SCOREABLE_SEASON must equal SBV_TRUSTWORTHY_ADP_START_SEASON + "
            f"SBV_MIN_PRIOR_SEASONS ({SBV_TRUSTWORTHY_ADP_START_SEASON} + "
            f"{SBV_MIN_PRIOR_SEASONS} = {SBV_TRUSTWORTHY_ADP_START_SEASON + SBV_MIN_PRIOR_SEASONS}), "
            f"got {SBV_FIRST_SCOREABLE_SEASON}"
        )
    if not isinstance(SBV_MIN_PRIOR_SEASONS, int) or SBV_MIN_PRIOR_SEASONS < 1:
        errors.append(f"SBV_MIN_PRIOR_SEASONS must be a positive integer, got {SBV_MIN_PRIOR_SEASONS}")

    # --- season length ---
    if SBV_SEASON_LENGTH_16_GAME >= SBV_SEASON_LENGTH_17_GAME:
        errors.append(
            f"SBV_SEASON_LENGTH_16_GAME ({SBV_SEASON_LENGTH_16_GAME}) must be less than "
            f"SBV_SEASON_LENGTH_17_GAME ({SBV_SEASON_LENGTH_17_GAME})"
        )
    if not isinstance(SBV_SEASON_LENGTH_ERA_CUTOFF, int):
        errors.append(f"SBV_SEASON_LENGTH_ERA_CUTOFF must be an integer season, got {SBV_SEASON_LENGTH_ERA_CUTOFF}")

    # --- shrinkage k ---
    if not isinstance(SBV_SHRINKAGE_K, (int, float)) or SBV_SHRINKAGE_K <= 0:
        errors.append(f"SBV_SHRINKAGE_K must be a positive number, got {SBV_SHRINKAGE_K}")

    # --- production composite weights sum to 1.0 ---
    prod_weight_sum = SBV_PRODUCTION_WEIGHT_AATP + SBV_PRODUCTION_WEIGHT_PPG_EQ
    if abs(prod_weight_sum - 1.0) > 1e-6:
        errors.append(
            f"SBV_PRODUCTION_WEIGHT_AATP + SBV_PRODUCTION_WEIGHT_PPG_EQ must sum to 1.0, "
            f"got {prod_weight_sum}"
        )

    # --- position-complete, positive-valued dicts ---
    for name, d in [
        ("SBV_PRODUCTION_GATE_FLOOR", SBV_PRODUCTION_GATE_FLOOR),
        ("SBV_REPLACEMENT_RANK_CUTOFFS", SBV_REPLACEMENT_RANK_CUTOFFS),
        ("SBV_STAR_THRESHOLD", SBV_STAR_THRESHOLD),
        ("SBV_MMC_OPPORTUNITY_PROBABILITY", SBV_MMC_OPPORTUNITY_PROBABILITY),
        ("SBV_MMC_REPLACEMENT_PPG", SBV_MMC_REPLACEMENT_PPG),
        ("SBV_MMC_USAGE_DEFINITION", SBV_MMC_USAGE_DEFINITION),
    ]:
        _check_position_keys(name, d)

    for pos, floor in SBV_PRODUCTION_GATE_FLOOR.items():
        if not isinstance(floor, (int, float)) or floor <= 0:
            errors.append(f"SBV_PRODUCTION_GATE_FLOOR['{pos}'] must be a positive number, got {floor}")
    for pos, thr in SBV_STAR_THRESHOLD.items():
        if not isinstance(thr, (int, float)) or thr <= 0:
            errors.append(f"SBV_STAR_THRESHOLD['{pos}'] must be a positive number, got {thr}")

    # --- threshold ORDERING: the production gate must be a lower bar
    # than the final Star threshold for every position -- the gate is
    # a prerequisite to be "in the conversation," not the final bar
    # itself (section 11's four-step processing order depends on this
    # actually being true, not just documented as true). ---
    for pos in SBV_POSITIONS:
        if pos in SBV_PRODUCTION_GATE_FLOOR and pos in SBV_STAR_THRESHOLD:
            if SBV_PRODUCTION_GATE_FLOOR[pos] >= SBV_STAR_THRESHOLD[pos]:
                errors.append(
                    f"SBV_PRODUCTION_GATE_FLOOR['{pos}'] ({SBV_PRODUCTION_GATE_FLOOR[pos]}) "
                    f"must be strictly less than SBV_STAR_THRESHOLD['{pos}'] "
                    f"({SBV_STAR_THRESHOLD[pos]}) -- the gate must be an easier bar than "
                    "the final threshold"
                )

    # --- replacement definition ---
    for pos, cutoff in SBV_REPLACEMENT_RANK_CUTOFFS.items():
        if not isinstance(cutoff, int) or cutoff <= 0:
            errors.append(f"SBV_REPLACEMENT_RANK_CUTOFFS['{pos}'] must be a positive integer, got {cutoff}")
    flex_sum = sum(SBV_REPLACEMENT_FLEX_ALLOCATION.values())
    if abs(flex_sum - 1.0) > 1e-6:
        errors.append(f"SBV_REPLACEMENT_FLEX_ALLOCATION must sum to 1.0, got {flex_sum}")
    if not isinstance(SBV_REPLACEMENT_WINDOW, int) or SBV_REPLACEMENT_WINDOW <= 0:
        errors.append(f"SBV_REPLACEMENT_WINDOW must be a positive integer, got {SBV_REPLACEMENT_WINDOW}")

    # --- positional-offset / recency settings ---
    if not SBV_ROUND_OFFSET_POSITIONS.issubset(set(SBV_POSITIONS)):
        errors.append(f"SBV_ROUND_OFFSET_POSITIONS must be a subset of {SBV_POSITIONS}, got {SBV_ROUND_OFFSET_POSITIONS}")
    if not SBV_RECENCY_POSITIONS.issubset(set(SBV_POSITIONS)):
        errors.append(f"SBV_RECENCY_POSITIONS must be a subset of {SBV_POSITIONS}, got {SBV_RECENCY_POSITIONS}")
    if not isinstance(SBV_RECENCY_HALF_LIFE_YEARS, (int, float)) or SBV_RECENCY_HALF_LIFE_YEARS <= 0:
        errors.append(f"SBV_RECENCY_HALF_LIFE_YEARS must be a positive number, got {SBV_RECENCY_HALF_LIFE_YEARS}")

    # --- lambda ---
    if not isinstance(SBV_LAMBDA, (int, float)) or not (0 < SBV_LAMBDA < 1):
        errors.append(f"SBV_LAMBDA must be a number strictly between 0 and 1, got {SBV_LAMBDA}")

    # --- MMC opportunity probabilities in (0, 1), replacement PPG positive ---
    for pos, p in SBV_MMC_OPPORTUNITY_PROBABILITY.items():
        if not isinstance(p, (int, float)) or not (0 < p < 1):
            errors.append(f"SBV_MMC_OPPORTUNITY_PROBABILITY['{pos}'] must be in (0, 1), got {p}")
    for pos, ppg in SBV_MMC_REPLACEMENT_PPG.items():
        if not isinstance(ppg, (int, float)) or ppg <= 0:
            errors.append(f"SBV_MMC_REPLACEMENT_PPG['{pos}'] must be a positive number, got {ppg}")
    for pos, usage in SBV_MMC_USAGE_DEFINITION.items():
        if not isinstance(usage, dict) or "stat" not in usage or "min" not in usage:
            errors.append(f"SBV_MMC_USAGE_DEFINITION['{pos}'] must be a dict with 'stat' and 'min' keys, got {usage}")
        elif not isinstance(usage["min"], (int, float)) or usage["min"] <= 0:
            errors.append(f"SBV_MMC_USAGE_DEFINITION['{pos}']['min'] must be a positive number, got {usage['min']}")
    if not isinstance(SBV_MMC_ROLE_CONDITIONAL_DISCOUNT, (int, float)) or not (0 < SBV_MMC_ROLE_CONDITIONAL_DISCOUNT < 1):
        errors.append(
            f"SBV_MMC_ROLE_CONDITIONAL_DISCOUNT must be a number strictly between 0 and 1, got "
            f"{SBV_MMC_ROLE_CONDITIONAL_DISCOUNT}"
        )

    # --- acquisition-cost classifier thresholds ---
    if not isinstance(SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK, int) or SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK < 1:
        errors.append(
            f"SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK must be a positive integer, got "
            f"{SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK}"
        )
    if not isinstance(SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES, int) or SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES < 1:
        errors.append(
            f"SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES must be a positive integer, got "
            f"{SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES}"
        )
    if not isinstance(SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS, (int, float)) or SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS <= 0:
        errors.append(
            f"SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS must be a positive number, got "
            f"{SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS}"
        )
    if not isinstance(SBV_CLASSIFIER_DAY_1_2_MAX_ROUND, int) or not (1 <= SBV_CLASSIFIER_DAY_1_2_MAX_ROUND < 7):
        errors.append(
            f"SBV_CLASSIFIER_DAY_1_2_MAX_ROUND must be an integer in [1, 7), got "
            f"{SBV_CLASSIFIER_DAY_1_2_MAX_ROUND}"
        )
    if not isinstance(SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT, (int, float)) or not (0 < SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT < 100):
        errors.append(
            f"SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT must be in (0, 100), got "
            f"{SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT}"
        )

    # --- MFL settings ---
    if not isinstance(SBV_MFL_AVAILABLE_FROM_SEASON, int):
        errors.append(f"SBV_MFL_AVAILABLE_FROM_SEASON must be an integer season, got {SBV_MFL_AVAILABLE_FROM_SEASON}")
    if SBV_MFL_PERIOD != "AUG15":
        errors.append(
            f"SBV_MFL_PERIOD must be 'AUG15' -- the only period verified to be a clean "
            f"preseason snapshot (see docs/ADP_SOURCE_MATRIX.md), got {SBV_MFL_PERIOD!r}"
        )
    if not isinstance(SBV_MFL_MIN_REQUEST_DELAY_SECONDS, (int, float)) or SBV_MFL_MIN_REQUEST_DELAY_SECONDS <= 0:
        errors.append(
            f"SBV_MFL_MIN_REQUEST_DELAY_SECONDS must be a positive number, got "
            f"{SBV_MFL_MIN_REQUEST_DELAY_SECONDS}"
        )
    if not isinstance(SBV_MFL_MAX_RETRIES, int) or SBV_MFL_MAX_RETRIES < 1:
        errors.append(f"SBV_MFL_MAX_RETRIES must be a positive integer, got {SBV_MFL_MAX_RETRIES}")
    if not isinstance(SBV_MFL_BACKOFF_BASE_SECONDS, (int, float)) or SBV_MFL_BACKOFF_BASE_SECONDS <= 0:
        errors.append(
            f"SBV_MFL_BACKOFF_BASE_SECONDS must be a positive number, got {SBV_MFL_BACKOFF_BASE_SECONDS}"
        )
    if not isinstance(SBV_MFL_REQUEST_TIMEOUT_SECONDS, (int, float)) or SBV_MFL_REQUEST_TIMEOUT_SECONDS <= 0:
        errors.append(
            f"SBV_MFL_REQUEST_TIMEOUT_SECONDS must be a positive number, got "
            f"{SBV_MFL_REQUEST_TIMEOUT_SECONDS}"
        )

    # --- status / provenance enums: no duplicates ---
    if len(SBV_STATUSES) != len(set(SBV_STATUSES)):
        errors.append(f"SBV_STATUSES must not contain duplicates, got {SBV_STATUSES}")
    if len(SBV_PROVENANCE_TYPES) != len(set(SBV_PROVENANCE_TYPES)):
        errors.append(f"SBV_PROVENANCE_TYPES must not contain duplicates, got {SBV_PROVENANCE_TYPES}")
    if len(SBV_STATUSES) != 7:
        errors.append(f"SBV_STATUSES must have exactly 7 values (section 11), got {len(SBV_STATUSES)}")

    # --- artifact paths: non-empty strings with the expected extension ---
    for name, path, expected_ext in [
        ("SBV_OUTPUT_PARQUET_PATH", SBV_OUTPUT_PARQUET_PATH, ".parquet"),
        ("SBV_OUTPUT_CSV_EXPORT_PATH", SBV_OUTPUT_CSV_EXPORT_PATH, ".csv"),
        ("SBV_OUTPUT_CSV_SCHEMA_PATH", SBV_OUTPUT_CSV_SCHEMA_PATH, ".md"),
        ("SBV_EXPECTED_PRODUCTION_LOOKUP_PATH", SBV_EXPECTED_PRODUCTION_LOOKUP_PATH, ".parquet"),
        ("SBV_MMC_2010_OVERRIDE_PATH", SBV_MMC_2010_OVERRIDE_PATH, ".csv"),
    ]:
        if not isinstance(path, str) or not path.strip():
            errors.append(f"{name} must be a non-empty string, got {path!r}")
        elif not path.endswith(expected_ext):
            errors.append(f"{name} must end with '{expected_ext}', got {path!r}")

    # --- manual-override eligible seasons: non-empty, all ints, no duplicates ---
    if not SBV_MMC_MANUAL_OVERRIDE_SEASONS:
        errors.append("SBV_MMC_MANUAL_OVERRIDE_SEASONS must not be empty")
    if len(SBV_MMC_MANUAL_OVERRIDE_SEASONS) != len(set(SBV_MMC_MANUAL_OVERRIDE_SEASONS)):
        errors.append(
            f"SBV_MMC_MANUAL_OVERRIDE_SEASONS must not contain duplicates, "
            f"got {SBV_MMC_MANUAL_OVERRIDE_SEASONS}"
        )
    for season in SBV_MMC_MANUAL_OVERRIDE_SEASONS:
        if not isinstance(season, int):
            errors.append(f"SBV_MMC_MANUAL_OVERRIDE_SEASONS entries must be integers, got {season!r}")

    # --- 2010 override disallowed source values: non-empty, lowercase, no duplicates ---
    if not SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES:
        errors.append("SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES must not be empty")
    if len(SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES) != len(set(SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES)):
        errors.append(
            f"SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES must not contain duplicates, "
            f"got {SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES}"
        )
    for value in SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES:
        if not isinstance(value, str) or value != value.lower() or not value.strip():
            errors.append(
                f"SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES entries must be non-empty "
                f"lowercase strings (matching is case-insensitive at the value level, not "
                f"the definition), got {value!r}"
            )

    if errors:
        raise ValueError(
            "Invalid SBV configuration in config.py:\n  - " + "\n  - ".join(errors)
        )


# --- 2025 MFL ADP: canonical raw value + QB/TE sensitivity-ordering field ---
# NOT under the SBV_* prefix: this feeds the whole master DB (both
# LWI's overall_adp_model and SBV's expected-production fitting), not
# an SBV-only adjustment -- see the project-wide-integration decision
# in docs/ADP_SOURCE_MATRIX.md's 2025 investigation entries.
#
# REVISED 2026-07 (supersedes the original "Method B corrects
# overall_adp" design): a historical-reconstruction validation study
# (docs/ADP_SOURCE_MATRIX.md's "MFL correction study" entries) found
# that Method B's quantile-mapped output is mathematically RANK-scale
# (inherited from FFToday avg_rank, itself an average of platform
# RANKS), not genuine mean-pick ADP -- writing it into overall_adp
# would silently recreate the same rank-vs-ADP incompatibility that
# already disqualified FFToday from canonical status. A follow-up
# historical FFC rank-to-ADP reconstruction study tested whether a
# defensible conversion exists; walk-forward validation across
# 2014-2024 showed the naive "rank IS the ADP" baseline beats every
# tested historical curve on every metric -- no conversion clears the
# bar. Per the pre-committed fallback rule: raw MFL AUG15 mean_adp is
# the canonical overall_adp for ALL FOUR positions (QB/RB/WR/TE alike)
# -- it preserves genuine mean-pick units and historical comparability,
# even though the QB/TE source bias documented below remains
# uncorrected in the number actually consumed downstream. Method B's
# output survives only as a disclosed, NEVER-CONSUMED sensitivity
# ordering field -- see MFL_2025_SENSITIVITY_RANK_FIELD and
# tests/test_mfl_2025_adp_correction.py's
# TestSensitivityFieldNeverConsumedDownstream for the mechanical
# guarantee.
#
# Confidence in the underlying QB/TE ORDERING bias (not adopted as a
# numeric correction, but still real, disclosed evidence -- see the
# two-round validation study in ADP_SOURCE_MATRIX.md): QB -- HIGH
# confidence. TE -- MODERATE confidence (ESPN/Sleeper favor Method B's
# ordering, RTSports favors raw MFL's ordering on median error --
# genuine market-source disagreement, disclosed not concealed). RB/WR
# -- no correction ever proposed; raw MFL already agrees closely with
# independent consensus for those positions.
MFL_2025_CORRECTION_POSITIONS = {"QB", "TE"}
MFL_2025_CORRECTION_METHOD_NAME = "mfl_2025_qb_te_quantile_mapping_v2_rank_n_minus_1"
MFL_2025_CORRECTION_CALIBRATION_PATH = "data/manual/mfl_2025_qb_te_adp_correction_calibration.csv"
# Distinct, honest source label for every 2025 MFL-derived row, every
# position alike -- the SOURCE is MFL AUG15 either way; the disclosed
# QB/TE bias is a separate, documented fact (see above), never baked
# into the source label itself and never conflated with
# FFC/FFToday/FantasyPros' existing adp_source values.
MFL_2025_ADP_SOURCE = "mfl_aug15_2025"
# Field name deliberately says RANK, not ADP -- see module docstring
# in scripts/mfl_2025_adp_correction.py. Populated only for QB/TE;
# NULL for RB/WR. Never read by any scoring/eligibility consumer --
# mechanically enforced, not just documented.
MFL_2025_SENSITIVITY_RANK_FIELD = "mfl_2025_sensitivity_market_rank"


def validate_mfl_2025_correction_config():
    """Fail loudly on invalid 2025-correction configuration -- mirrors
    validate_sbv_config()'s role and calling convention."""
    errors = []

    if not MFL_2025_CORRECTION_POSITIONS:
        errors.append("MFL_2025_CORRECTION_POSITIONS must not be empty")
    if not MFL_2025_CORRECTION_POSITIONS.issubset(set(SBV_POSITIONS)):
        errors.append(
            f"MFL_2025_CORRECTION_POSITIONS must be a subset of SBV_POSITIONS "
            f"{SBV_POSITIONS}, got {MFL_2025_CORRECTION_POSITIONS}"
        )
    if "RB" in MFL_2025_CORRECTION_POSITIONS or "WR" in MFL_2025_CORRECTION_POSITIONS:
        errors.append(
            "MFL_2025_CORRECTION_POSITIONS must not include RB or WR -- explicitly "
            "excluded by the 2026-07 decision (raw MFL already agrees closely with "
            "independent consensus for those positions)"
        )
    if not MFL_2025_CORRECTION_METHOD_NAME or not isinstance(MFL_2025_CORRECTION_METHOD_NAME, str):
        errors.append("MFL_2025_CORRECTION_METHOD_NAME must be a non-empty string")
    if not MFL_2025_CORRECTION_CALIBRATION_PATH.endswith(".csv"):
        errors.append("MFL_2025_CORRECTION_CALIBRATION_PATH must end in .csv")
    if not MFL_2025_ADP_SOURCE or not isinstance(MFL_2025_ADP_SOURCE, str):
        errors.append("MFL_2025_ADP_SOURCE must be a non-empty string")
    if not MFL_2025_SENSITIVITY_RANK_FIELD or "adp" in MFL_2025_SENSITIVITY_RANK_FIELD.lower():
        errors.append(
            "MFL_2025_SENSITIVITY_RANK_FIELD must be a non-empty string and must NOT "
            "contain 'adp' -- it is a rank, not an ADP value, and must never be named "
            "in a way that invites confusing the two"
        )

    if errors:
        raise ValueError(
            "Invalid 2025 MFL correction configuration in config.py:\n  - " + "\n  - ".join(errors)
        )
