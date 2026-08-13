import copy

import pandas as pd
import pytest

from lib.dataset2.bust_reference import apply_bust_reference, fit_bust_reference


def _rows():
    return pd.DataFrame([
        {"outcome_season": season, "position": "RB", "adp_round": 2,
         "games_played": 16, "bust_primary_eligible": True,
         "score_like": float(season - 2009), "P": float(season - 2009)}
        for season in range(2010, 2021)
    ] + [
        {"outcome_season": 2021, "position": "RB", "adp_round": 2,
         "games_played": 17, "bust_primary_eligible": True,
         "score_like": -999.0, "P": -999.0}
    ])


def test_fit_uses_only_2010_2020_and_holdout_mutation_cannot_change_hash():
    rows = _rows()
    first = fit_bust_reference(rows)
    mutated = rows.copy()
    mutated.loc[mutated["outcome_season"] == 2021, ["score_like", "P"]] = 999999.0
    second = fit_bust_reference(mutated)
    assert first == second
    assert first["eligible_fit_rows"] == 11
    assert first["fit_end_season"] == 2020


def test_apply_uses_frozen_distribution_and_rejects_tampering():
    rows = _rows()
    reference = fit_bust_reference(rows)
    holdout = rows[rows["outcome_season"] == 2021]
    result = apply_bust_reference(holdout, reference)
    # 2021+ shares the approved 2011+ era category, but is ranked only
    # against the frozen 2011-2020 discovery distribution.
    assert result.iloc[0]["bust_primary_assignment_method"] == "era_specific_g_score"
    tampered = copy.deepcopy(reference)
    tampered["eligible_fit_rows"] = 12
    with pytest.raises(ValueError, match="hash mismatch"):
        apply_bust_reference(holdout, tampered)
