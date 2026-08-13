"""
scripts/2025_adp_integration.py

Wires the governed 147-league 2025 MFL reconstruction into the normal
ADP-clean pipeline. Both governed package roots are explicit inputs;
there is no diagnostic-directory default and no network fallback.

Appends real 2025 rows to data/processed/adp_clean_2006_2025.csv in
the EXACT schema 02_clean_adp.py already produces (season, source,
scoring_format, league_size, player_name_original,
player_name_normalized, position, team, overall_adp, adp_rank,
times_drafted, source_quality_flag) -- 2025 never goes through
01/02's FFC-based fetch (there is no FFC data for 2025 at all), this
is the narrow, documented substitute for that one season.

The governed inputs are parsed/re-serialized audit-cache snapshots,
not original MFL wire bytes and not a recovered original package.
Their manifest and hashes are validated before participation or mean
pick is derived. Players absent from all 147 drafts remain absent.

Does NOT run player_matching.py or write to the master DB itself --
that's 04_build_master_dataset.py's job, run unmodified afterward.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from player_matching import normalize_name  # noqa: E402
from mfl_2025_adp_correction import build_mfl_2025_adp_and_sensitivity, load_calibration  # noqa: E402
import config  # noqa: E402
from lib.mfl_2025_reconstruction import derive_governed_2025_participation  # noqa: E402
from lib.source_governance import DEFAULT_MANIFEST_PATH  # noqa: E402

ADP_CLEAN_PATH = REPO_ROOT / f"data/processed/adp_clean_{config.SEASONS[0]}_{config.SEASONS[-1]}.csv"
MFL_2025_SEASON = 2025

CANONICAL_COLUMNS = [
    "season", "source", "scoring_format", "league_size",
    "player_name_original", "player_name_normalized",
    "position", "team", "overall_adp", "adp_rank",
    "times_drafted", "source_quality_flag",
    "draft_selection_count", "draft_selection_denominator",
    "draft_selection_rate", "mfl_reconstruction_identity",
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
SOURCE_QUALITY_FLAG = "governed_mfl_147_offline_reconstruction"


def _mfl_name_to_first_last(name: str) -> str:
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def _load_governed_mfl_2025_adp(
    *, archive_root: Path, cache_root: Path, manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> pd.DataFrame:
    rows = derive_governed_2025_participation(
        archive_root=archive_root, cache_root=cache_root, manifest_path=manifest_path,
    )
    rows["player_name_original"] = rows["player_name_original"].map(_mfl_name_to_first_last)
    return rows


def build_2025_adp_clean_rows(
    *, archive_root: Path, cache_root: Path, manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> pd.DataFrame:
    mfl_raw = _load_governed_mfl_2025_adp(
        archive_root=archive_root, cache_root=cache_root, manifest_path=manifest_path,
    )
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
        "draft_selection_count": mfl_raw["draft_selection_count"].values,
        "draft_selection_denominator": mfl_raw["draft_selection_denominator"].values,
        "draft_selection_rate": mfl_raw["draft_selection_rate"].values,
        "mfl_reconstruction_identity": mfl_raw["mfl_reconstruction_identity"].values,
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


def integrate(*, archive_root: Path, cache_root: Path, manifest_path: Path = DEFAULT_MANIFEST_PATH):
    if not ADP_CLEAN_PATH.exists():
        raise FileNotFoundError(f"{ADP_CLEAN_PATH} must exist (from 02_clean_adp.py) before integrating 2025.")

    existing = pd.read_csv(ADP_CLEAN_PATH)
    if (existing["season"] == 2025).any():
        raise RuntimeError(
            f"{ADP_CLEAN_PATH} already has 2025 rows -- refusing to silently "
            f"append a duplicate season. Remove them first if re-integrating."
        )

    rows_2025 = build_2025_adp_clean_rows(
        archive_root=archive_root, cache_root=cache_root, manifest_path=manifest_path,
    )

    provenance_path = REPO_ROOT / "data/processed/adp_2025_provenance.csv"
    rows_2025[["player_name_original", "position", "overall_adp",
               "draft_selection_count", "draft_selection_denominator", "draft_selection_rate",
               "mfl_reconstruction_identity",
               "_overall_adp_mfl_raw", "_mfl_2025_sensitivity_market_rank"]].to_csv(provenance_path, index=False)
    print(f"Wrote 2025 provenance sidecar: {provenance_path} ({len(rows_2025)} rows)")

    combined = pd.concat(
        [existing, rows_2025[CANONICAL_COLUMNS]], ignore_index=True,
    ).sort_values(["season", "adp_rank"])
    combined.to_csv(ADP_CLEAN_PATH, index=False)
    print(f"Updated {ADP_CLEAN_PATH}: {len(existing)} -> {len(combined)} rows "
          f"({len(rows_2025)} real 2025 rows added, source={config.MFL_2025_ADP_SOURCE!r})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()
    integrate(archive_root=args.archive_root, cache_root=args.cache_root, manifest_path=args.manifest_path)
