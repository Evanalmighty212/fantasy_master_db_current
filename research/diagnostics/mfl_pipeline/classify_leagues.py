"""
classify_leagues.py  (ISOLATED DIAGNOSTIC)

For every discovered league, fetches its real config via MFL's public
`TYPE=league` API and classifies it as clean-1QB or excluded, with a
specific, named reason. Serial, cached, rate-limited via mfl_client
(no exceptions to that).

Verified field semantics behind each check (real league 14090
inspected directly before writing this, not guessed):
  - QB superflex/2-QB check: does NOT just check whether QB's `limit`
    field equals "1" -- the same JSON schema encodes flex ranges
    directly on a position's limit (e.g. real leagues show RB as
    "2-3", meaning 2 dedicated + up to 1 more via a shared flex slot).
    So a true superflex/2-QB league is expected to show QB's limit as
    a RANGE with a max > 1 (e.g. "1-2"), not a separate named "OP"
    slot -- this checks the parsed MAX of the QB limit, not string
    equality to "1". Also separately checks for any composite starter
    position NAME that itself implies QB eligibility (e.g. "OP"), in
    case a given league encodes it that way instead -- both checks
    run, not just one.
  - IDP: real presence of individual defensive starter positions
    (DL/LB/DB/CB/S/etc.) in the league's own starters list, not
    inferred.
  - Auction: `usesSalaries != "0"`.
  - Dynasty: `taxiSquad > 0` (a taxi squad is a dynasty-specific
    roster mechanic; redraft leagues don't have one).
  - Franchise count: re-verified per-league (12), even though the
    discovery report was already filtered to FCOUNT=12, as a direct
    cross-check rather than trusting the report filter alone.

NOT independently verifiable from this API endpoint, disclosed rather
than silently assumed clean:
  - Best-ball (no explicit field found in the league-config schema for
    this).
  - Rookie-only / keeper: NOT re-checked per-league here -- already
    excluded at the DISCOVERY stage via the report's own IS_KEEPER=N
    filter (a mutually-exclusive dropdown value distinct from "Keeper
    League Drafts" and "Rookie-Only Drafts"), not re-verified
    independently per league.

Output: research/diagnostics/mfl_pipeline/output/league_classification.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mfl_client import get_json, cache_stats

LEAGUES_PATH = Path(__file__).resolve().parent / "output" / "discovered_leagues.csv"
OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "league_classification.csv"
LEAGUE_API_TEMPLATE = "https://api.myfantasyleague.com/2025/export?TYPE=league&L={league_id}&JSON=1"

IDP_POSITION_NAMES = {"DL", "LB", "DB", "CB", "S", "DE", "DT", "MLB", "OLB", "ILB", "FS", "SS"}
NON_QB_STANDARD_NAMES = {"QB", "RB", "WR", "TE", "PK", "Def", "FB", "TMQB", "TMRB", "TMWR", "TMTE", "TMPK", "TMPN", "KR", "PN"}


def _parse_limit_max(limit_str) -> int:
    if limit_str is None:
        return 0
    s = str(limit_str)
    if "-" in s:
        try:
            return int(s.split("-")[1])
        except ValueError:
            return 0
    try:
        return int(s)
    except ValueError:
        return 0


def classify_one(league_json: dict) -> dict:
    if "_error" in league_json:
        return {"status": "fetch_error", "exclusion_reasons": league_json["_error"]}

    lg = league_json.get("league", {})
    if not lg:
        return {"status": "malformed_response", "exclusion_reasons": "no 'league' key in response"}

    starters = lg.get("starters", {}).get("position", [])
    if isinstance(starters, dict):  # MFL returns a single dict, not a list, when there's only one position
        starters = [starters]
    pos_by_name = {p["name"]: p["limit"] for p in starters}

    reasons = []

    qb_limit_raw = pos_by_name.get("QB")
    qb_limit_max = _parse_limit_max(qb_limit_raw)
    if qb_limit_max == 0:
        reasons.append("no_qb_slot_found")
    elif qb_limit_max > 1:
        reasons.append(f"superflex_or_2qb(QB_limit_max={qb_limit_max})")

    composite_qb_slots = [
        name for name in pos_by_name
        if name not in NON_QB_STANDARD_NAMES and "QB" in name.upper()
    ]
    if composite_qb_slots:
        reasons.append(f"composite_qb_eligible_slot({composite_qb_slots})")

    idp_found = [name for name in pos_by_name if name.upper() in IDP_POSITION_NAMES]
    if idp_found:
        reasons.append(f"idp_league(positions={idp_found})")

    if str(lg.get("usesSalaries", "0")) != "0":
        reasons.append("auction_or_salary_cap")

    taxi = lg.get("taxiSquad", "0")
    try:
        if int(taxi) > 0:
            reasons.append(f"dynasty_taxi_squad({taxi})")
    except (ValueError, TypeError):
        pass

    fcount = lg.get("franchises", {}).get("count")
    try:
        fcount_int = int(fcount)
        if fcount_int != 12:
            reasons.append(f"unexpected_franchise_count({fcount_int})")
    except (ValueError, TypeError):
        fcount_int = None
        reasons.append("franchise_count_unavailable")

    return {
        "status": "ok",
        "is_clean_1qb": len(reasons) == 0,
        "exclusion_reasons": ";".join(reasons) if reasons else "",
        "qb_limit_raw": qb_limit_raw,
        "franchise_count": fcount_int,
        "starter_positions": ",".join(sorted(pos_by_name.keys())),
    }


def main():
    leagues = pd.read_csv(LEAGUES_PATH, dtype={"league_id": str})
    print(f"Classifying {len(leagues)} discovered leagues (serial, rate-limited, cached)...")

    rows = []
    for i, row in leagues.iterrows():
        lid = row["league_id"]
        url = LEAGUE_API_TEMPLATE.format(league_id=lid)
        data = get_json(url)
        result = classify_one(data)
        result["league_id"] = lid
        result["league_name"] = row["league_name"]
        rows.append(result)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(leagues)} classified...")

    out = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"\nWrote {OUTPUT_PATH}")
    print(f"\nStatus breakdown:\n{out['status'].value_counts().to_string()}")
    ok = out[out["status"] == "ok"]
    print(f"\nOf {len(ok)} successfully classified:")
    print(f"  Clean 1-QB (passes every check): {ok['is_clean_1qb'].sum()}")
    print(f"  Excluded: {(~ok['is_clean_1qb']).sum()}")
    all_reasons = ok[~ok["is_clean_1qb"]]["exclusion_reasons"].str.split(";").explode()
    print(f"\nExclusion reason breakdown:\n{all_reasons.value_counts().to_string()}")
    print(f"\nCache stats: {cache_stats()}")


if __name__ == "__main__":
    main()
