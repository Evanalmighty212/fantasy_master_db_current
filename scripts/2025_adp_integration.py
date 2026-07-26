"""
scripts/2025_adp_integration.py

Commit E, step 1: wires the approved 2025 canonical ADP source (raw
MFL AUG15 mean_adp, all four positions -- see docs/ADP_SOURCE_MATRIX.md
and config.py's MFL_2025_* block for the full decision record) into
the normal ADP-clean pipeline, so 04_build_master_dataset.py picks up
2025 automatically, unmodified, exactly like every other season.

Appends real 2025 rows to data/processed/adp_clean_2006_2025.csv in
the EXACT schema 02_clean_adp.py already produces (season, source,
scoring_format, league_size, player_name_original,
player_name_normalized, position, team, overall_adp, adp_rank,
times_drafted, source_quality_flag) -- 2025 never goes through
01/02's FFC-based fetch (there is no FFC data for 2025 at all), this
is the narrow, documented substitute for that one season.

RAW SOURCE (2026-07 fix -- see docs/ADP_SOURCE_MATRIX.md's provenance
audit entry): the real 2025 MFL AUG15 aggregate report, fetched and
cached via mfl_client.py's EXISTING fetch/manifest/integrity
conventions -- the exact same mechanism every other season's MFL data
already goes through (see mfl_historical_backfill.py). A cache hit
(the validated production snapshot already merged into
scripts/mfl_source_manifest.json) returns silently, no network call.

An earlier version of this script read
research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv
instead -- an EXPLICITLY ISOLATED research artifact (per that
pipeline's own README: "never wired into the canonical ADP pipeline
and not used by anything under scripts/"). That was a real wiring
bug, not a methodology choice: it fed a different, per-league-
draft-reconstructed population (from ~193 individually classified
league drafts) into overall_adp for every position, instead of MFL's
own AUG15 aggregate report (from mfl_client.py's cached
data/raw/mfl/adp_2025_period_aug15.json, 3,597 real drafts as of the
2026-07 fetch) -- confirmed to differ materially for real players
(e.g. Travis Hunter: 79.42 from the isolated pipeline vs. 60.90 from
the real aggregate, an 18.5-pick gap, enough to shift adp_round).
Fixed here by replacing the isolated-pipeline read with
_load_production_mfl_2025_adp() below. See
tests/test_2025_adp_integration.py::TestProductionSourceRegression
for the named-player regression pin, and
tests/test_no_isolated_research_dependency.py for the structural
guarantee that no production script reads that directory again.

Does NOT run player_matching.py or write to the master DB itself --
that's 04_build_master_dataset.py's job, run unmodified afterward.
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from player_matching import normalize_name  # noqa: E402
from mfl_2025_adp_correction import build_mfl_2025_adp_and_sensitivity, load_calibration  # noqa: E402
import config  # noqa: E402
import mfl_client  # noqa: E402

ADP_CLEAN_PATH = REPO_ROOT / f"data/processed/adp_clean_{config.SEASONS[0]}_{config.SEASONS[-1]}.csv"
MFL_2025_SEASON = 2025

CANONICAL_COLUMNS = [
    "season", "source", "scoring_format", "league_size",
    "player_name_original", "player_name_normalized",
    "position", "team", "overall_adp", "adp_rank",
    "times_drafted", "source_quality_flag",
]

# Narrow, individually-documented exclusions -- same precedent as the
# Vick 2010 exception in acquisition_cost.py: a specific, reviewed
# case, not a generalized rejection mechanism (player_name_overrides.csv
# only supports POSITIVE identity assertions; there is no negative-
# override mechanism in this pipeline, a real, disclosed limitation --
# see docs/ADP_SOURCE_MATRIX.md's Commit D audit entry). Reviewed and
# explicitly rejected during the 2025 matching audit: the real Amari
# Cooper has zero 2025 nflverse stats rows (confirmed directly), so
# his real MFL ADP entry has no valid target to match against --
# left unexcluded, match_players() fuzzy-matches him to the unrelated
# "Darius Cooper" (score 80.0, exactly the review floor) every time,
# since the underlying algorithm is run unmodified. Excluding this one
# MFL row here is the narrowest fix available without inventing new
# matching infrastructure -- it leaves him correctly no_adp_match
# (an honest "we have a real ADP number but can't validly attach it
# to a player_id this season"), not silently mismatched.
EXCLUDED_2025_ADP_ROWS = {
    ("Amari Cooper", "WR"): "Real Amari Cooper has zero 2025 nflverse stats rows; "
        "fuzzy-matches to the unrelated 'Darius Cooper' at the review floor (80.0). "
        "Reviewed and rejected 2026-07 -- see docs/ADP_SOURCE_MATRIX.md.",
}

# Distinct from FFC's "verified_clean" -- real, verified MFL data, but
# with the disclosed QB/TE ordering bias on record (see
# docs/ADP_SOURCE_MATRIX.md). Never silently equated to FFC's own
# quality level.
SOURCE_QUALITY_FLAG = "verified_mfl_raw_canonical"


def _mfl_name_to_first_last(name: str) -> str:
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def _load_production_mfl_2025_adp() -> pd.DataFrame:
    """Loads the real 2025 MFL AUG15 raw report via mfl_client.py's
    existing fetch/cache/integrity conventions -- the SAME mechanism
    every other season's MFL data already goes through, not a second
    parser. A cache hit (the validated production snapshot already
    merged into scripts/mfl_source_manifest.json) returns silently, no
    network call; a missing/mismatched cache raises loudly exactly as
    it would for any other season -- see mfl_client.py's own docstring
    for the full integrity model.

    Returns one row per MFL player_id with a real adp entry:
    player_id, player_name_original (first-last), position, team,
    mfl_mean_adp (MFL's own averagePick field -- a genuine mean-pick
    value), times_drafted (MFL's own draftsSelectedIn field -- real
    selection-count metadata, not a reconstructed count from a
    different population)."""
    adp_resp = mfl_client.fetch_adp(MFL_2025_SEASON)
    players_resp = mfl_client.fetch_players(MFL_2025_SEASON)
    players_by_id = {p["id"]: p for p in players_resp["players"]["player"]}

    rows = []
    for a in adp_resp["adp"]["player"]:
        pid = a["id"]
        meta = players_by_id.get(pid)
        if meta is None:
            continue  # a real adp entry with no matching players-report row -- rare, skip rather than guess a position/team
        rows.append({
            "player_id": pid,
            "player_name_original": _mfl_name_to_first_last(meta.get("name", "")),
            "position": meta.get("position"),
            "team": meta.get("team"),
            "mfl_mean_adp": float(a["averagePick"]),
            "times_drafted": int(a["draftsSelectedIn"]),
        })
    return pd.DataFrame(rows)


def build_2025_adp_clean_rows() -> pd.DataFrame:
    mfl_raw = _load_production_mfl_2025_adp()
    mfl_raw = mfl_raw[mfl_raw["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    mfl_raw["player_name"] = mfl_raw["player_name_original"]

    calibration = load_calibration(str(REPO_ROOT / config.MFL_2025_CORRECTION_CALIBRATION_PATH))
    built = build_mfl_2025_adp_and_sensitivity(
        mfl_raw[["player_id", "player_name", "position", "mfl_mean_adp"]], calibration=calibration,
    )

    out = pd.DataFrame({
        "season": 2025,
        "source": config.MFL_2025_ADP_SOURCE,
        "scoring_format": "PPR",
        "league_size": 12,
        "player_name_original": mfl_raw["player_name_original"].values,
        "player_name_normalized": mfl_raw["player_name_original"].apply(normalize_name).values,
        "position": built["position"].values,
        "team": mfl_raw["team"].values,
        "overall_adp": built["overall_adp"].values,
        "times_drafted": mfl_raw["times_drafted"].values,
        "source_quality_flag": SOURCE_QUALITY_FLAG,
        # NOT part of 02_clean_adp.py's real schema and NOT in
        # CANONICAL_COLUMNS -- these two are dropped before writing
        # adp_clean and live ONLY in the provenance sidecar CSV
        # (data/processed/adp_2025_provenance.csv, regenerated by
        # integrate() below on every run). Deliberately kept out of
        # the master DB: an earlier version of this pipeline had
        # mfl_2025_sensitivity_market_rank appear in the master DB
        # anyway, via an uncommitted manual step that 04_build_
        # master_dataset.py's own committed code could not reproduce
        # -- exactly the kind of gap docs/ADP_SOURCE_MATRIX.md's
        # provenance audit flagged. The sidecar CSV is the single,
        # fully reproducible home for both fields; "disclosed and
        # auditable" does not require living inside the master DB
        # table itself.
        "_mfl_2025_sensitivity_market_rank": built["mfl_2025_sensitivity_market_rank"].values,
        "_overall_adp_mfl_raw": built["overall_adp_mfl_raw"].values,
    })

    for (name, pos), reason in EXCLUDED_2025_ADP_ROWS.items():
        mask = (out["player_name_original"] == name) & (out["position"] == pos)
        n = mask.sum()
        if n > 0:
            print(f"  Excluding {n} row(s) for {name!r} ({pos}): {reason}")
            out = out[~mask].copy()

    # adp_rank: identical convention to 02_clean_adp.py -- computed per
    # (season, scoring_format), method="first", after all rows are present.
    out["adp_rank"] = (
        out.groupby(["season", "scoring_format"])["overall_adp"]
        .rank(method="first", ascending=True)
        .astype("Int64")
    )
    return out


def integrate():
    if not ADP_CLEAN_PATH.exists():
        raise FileNotFoundError(f"{ADP_CLEAN_PATH} must exist (from 02_clean_adp.py) before integrating 2025.")

    existing = pd.read_csv(ADP_CLEAN_PATH)
    if (existing["season"] == 2025).any():
        raise RuntimeError(
            f"{ADP_CLEAN_PATH} already has 2025 rows -- refusing to silently "
            f"append a duplicate season. Remove them first if re-integrating."
        )

    rows_2025 = build_2025_adp_clean_rows()

    provenance_path = REPO_ROOT / "data/processed/adp_2025_provenance.csv"
    rows_2025[["player_name_original", "position", "overall_adp",
               "_overall_adp_mfl_raw", "_mfl_2025_sensitivity_market_rank"]].to_csv(provenance_path, index=False)
    print(f"Wrote 2025 provenance sidecar: {provenance_path} ({len(rows_2025)} rows)")

    combined = pd.concat(
        [existing, rows_2025[CANONICAL_COLUMNS]], ignore_index=True,
    ).sort_values(["season", "adp_rank"])
    combined.to_csv(ADP_CLEAN_PATH, index=False)
    print(f"Updated {ADP_CLEAN_PATH}: {len(existing)} -> {len(combined)} rows "
          f"({len(rows_2025)} real 2025 rows added, source={config.MFL_2025_ADP_SOURCE!r})")


if __name__ == "__main__":
    integrate()
