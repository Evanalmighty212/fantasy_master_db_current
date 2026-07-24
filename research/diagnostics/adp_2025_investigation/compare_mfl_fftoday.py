"""
compare_mfl_fftoday.py  (ISOLATED DIAGNOSTIC)

Compares MFL's reconstructed 2025 ADP (research/diagnostics/mfl_pipeline/)
against FFToday's 2025 PPR page's 3-source rank consensus (Sleeper,
RTSports, ESPN -- see fftoday_2025_ppr_consensus.csv, parsed from
https://www.fftoday.com/rankings/25_adp_ppr.html).

KNOWN PITFALL -- must filter to real skill positions BEFORE merging:
MFL's player table (research/diagnostics/mfl_pipeline/output/all_players.csv
and everything derived from it, including adp_all_non_keeper.csv) contains
up to 6 duplicate rows per NFL team under non-player, franchise-level
labels ("Def", "TMPK", "ST", "Off", "Coach", "PN"), all sharing the exact
same normalized team name (e.g. "denver broncos"). FFToday's page also has
27 real DEF rows using the same team names. Merging on normalized name
before restricting both sides to {QB, RB, WR, TE} lets one FFToday DEF row
match multiple MFL team-level duplicate rows, silently inflating the
overlap count -- this happened once already (reported as 348 overlapping
players; the real, position-consistent number is 228). filter_to_skill_positions()
below exists specifically to make that filtering happen before every merge,
not as an afterthought. test_compare_mfl_fftoday.py locks this in with a
synthetic fixture reproducing the exact collision.

Output: research/diagnostics/adp_2025_investigation/parsed/mfl_vs_fftoday_comparison.csv
"""

import re
from pathlib import Path

import pandas as pd

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

BASE_DIR = Path(__file__).resolve().parent
MFL_ADP_PATH = BASE_DIR.parent / "mfl_pipeline" / "output" / "adp_all_non_keeper.csv"
FFTODAY_PATH = BASE_DIR / "parsed" / "fftoday_2025_ppr_consensus.csv"
ESPN_BENCHMARK_PATH = (
    BASE_DIR.parent.parent / "benchmarks" / "espn_championship_rosters" / "championship_roster_players.csv"
)
OUTPUT_PATH = BASE_DIR / "parsed" / "mfl_vs_fftoday_comparison.csv"


def normalize_name(s) -> str:
    return re.sub(r"[.']", "", str(s)).lower().strip()


def mfl_name_to_normalized(s) -> str:
    """MFL player names are 'Last, First' -- reorder before normalizing."""
    if isinstance(s, str) and "," in s:
        s = " ".join(reversed([p.strip() for p in s.split(",", 1)]))
    return normalize_name(s)


def filter_to_skill_positions(df: pd.DataFrame, position_col: str) -> pd.DataFrame:
    """Restrict to real QB/RB/WR/TE rows. MUST be called on both sides of
    any MFL<->FFToday merge before merging -- see module docstring."""
    return df[df[position_col].isin(SKILL_POSITIONS)].copy()


def load_fftoday() -> pd.DataFrame:
    fft = pd.read_csv(FFTODAY_PATH)
    fft["player_norm"] = fft["player"].apply(normalize_name)
    for col in ("sleeper_rank", "rtsports_rank", "espn_rank", "avg_rank", "rk"):
        fft[col] = pd.to_numeric(fft[col], errors="coerce")
    fft = fft.rename(columns={"espn_rank": "fftoday_espn_rank"})
    return filter_to_skill_positions(fft, "position")


def load_mfl() -> pd.DataFrame:
    mfl = pd.read_csv(MFL_ADP_PATH)
    mfl["player_norm"] = mfl["name"].apply(mfl_name_to_normalized)
    return filter_to_skill_positions(mfl, "position")


def merge_mfl_fftoday(mfl_skill: pd.DataFrame, fft_skill: pd.DataFrame) -> pd.DataFrame:
    """Both inputs must already be skill-position-only (see
    filter_to_skill_positions) -- this function does not filter for you,
    so that callers can't accidentally skip the step and still get a
    plausible-looking result."""
    return mfl_skill.merge(
        fft_skill[["player_norm", "sleeper_rank", "rtsports_rank", "fftoday_espn_rank", "avg_rank", "position"]],
        on="player_norm", how="inner", suffixes=("", "_fft"),
    )


def summarize(merged: pd.DataFrame) -> None:
    total = len(merged)
    print(f"Total MFL<->FFToday skill-position overlap: {total}")
    position_sum = sum(len(merged[merged["position_fft"] == pos]) for pos in ("QB", "RB", "WR", "TE"))
    assert position_sum == total, (
        f"Position breakdown ({position_sum}) does not match total overlap ({total}) -- "
        f"this is the exact inconsistency caused by unfiltered team-level MFL rows. "
        f"Do not trust this output; re-check that both inputs were skill-position-filtered."
    )
    print(f"Position breakdown sums to total: {position_sum} == {total} (consistent)")

    for col in ("sleeper_rank", "rtsports_rank", "fftoday_espn_rank", "avg_rank"):
        sub = merged.dropna(subset=[col])
        r = sub["mean_adp"].corr(sub[col])
        mad = (sub["mean_adp"] - sub[col]).abs().median()
        print(f"  MFL vs {col}: n={len(sub)}, pearson_r={r:.4f}, median_abs_diff={mad:.2f}")


def main():
    mfl_skill = load_mfl()
    fft_skill = load_fftoday()
    merged = merge_mfl_fftoday(mfl_skill, fft_skill)
    summarize(merged)
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
