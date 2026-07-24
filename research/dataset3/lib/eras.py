"""
Shared era-bucket assignment, reused across Dataset 3 research scripts.

Buckets match docs/LEAGUE_WINNER_TRAITS_SPEC.md's proposed defaults
(pre-2011 / 2011-2020 / 2021+) -- explicitly INITIAL DEFAULTS per that
spec, not fixed boundaries, so revisiting them later is not a
violation of anything. Reusing the same buckets here rather than
inventing a second, different set of era cutoffs for Dataset 3
research specifically, so "this pattern is era-stable" means the same
thing in both places.
"""

ERA_BOUNDARIES = [
    (0, 2010, "pre_2011"),
    (2011, 2020, "2011_2020"),
    (2021, 9999, "2021_plus"),
]


def assign_era(season: int) -> str:
    for lo, hi, label in ERA_BOUNDARIES:
        if lo <= season <= hi:
            return label
    raise ValueError(f"Season {season} not covered by any era bucket")


def add_era_column(df, season_col="season", out_col="era"):
    df = df.copy()
    df[out_col] = df[season_col].apply(assign_era)
    return df
