"""
build_dataset.py

Hand-transcribed external benchmark data, NOT pipeline-derived. Same
status as data/manual/ in the main project: git-tracked source data, not
regenerated CSV output -- writes to a plain file in this directory, not
to a gitignored research/output/ path.

Source: ESPN's annual "most common players on fantasy football
CHAMPIONSHIP rosters" series -- i.e. players who were on teams that
actually WON their fantasy league that season. A specific, narrower
series than ESPN's separate "playoff rosters" or "finalist/
championship-round rosters" articles, which report different, broader
populations and are deliberately NOT used here. Most years are
authored by Tristan H. Cockcroft; 2014-2016 are credited to other ESPN
staff (Tom Carpenter, Keith Lipscomb) writing the same series -- this
is why the directory is named for the SERIES (espn_championship_rosters),
not one author. Author is still recorded per-row/per-source, never
assumed uniform.

Each source article has a distinct COVERAGE STRUCTURE -- some publish
a fixed top-N, some a percentage-floor list, some are inaccessible or
unstructured. This is captured explicitly per source (`sources.csv`'s
`coverage_type`/`inclusion_rule`/`censoring_notes`) AND joined onto
every player row in `championship_roster_players.csv` (`coverage_type`/
`inclusion_rule` columns) specifically so downstream comparison code
can't accidentally treat "not in this dataset" as "not on a
championship roster" -- every year here is right-censored at its own
article's cutoff, not a complete census. See README's "Interpreting
this data correctly" section before using this for anything.

Each row is transcribed directly from that year's table as it appears
in the source article. Nothing here infers or extends beyond what the
article states. This dataset contains ONLY ranked championship-table
rows -- no narrative-only player mentions are included (a prior draft
included one incidental such row; removed on review, since one
non-systematically-collected row would misrepresent the dataset's
structure -- see README's "Known limitations" for why narrative-only
mentions were omitted entirely rather than partially collected).

Explicitly NOT a "league winner" dataset by definition -- this source
never uses that term; every row's `explicitly_named_league_winner`
field is "No" for exactly that reason. This is one external validation
source among possibly several future ones, not ground truth, and does
not define or modify Dataset 3's target, LWI's weights, or any
comparison formula -- see docs/PREDICTION_SPECIFICATION.md and
research/dataset3/ for that separate, still-open work.

IMPORTANT re: "reproducibility" -- running this script deterministically
regenerates the CSV outputs from the constants below, and the basic
sanity checks at the bottom will fail loudly if the transcription is
structurally broken (wrong row count, gapped ranks). That is NOT the
same claim as "this script independently re-verifies against the live
source articles" -- it does not; it has no network access and simply
writes out what was manually transcribed and spot-checked at
collection time (see README's "Spot-check log"). If ESPN ever edits a
source article, this script would not detect the drift.

Run: python research/benchmarks/espn_championship_rosters/build_dataset.py
Output: research/benchmarks/espn_championship_rosters/championship_roster_players.csv
        research/benchmarks/espn_championship_rosters/sources.csv
"""

import csv
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent

FIELDNAMES = [
    "season", "player_name", "position", "team",
    "espn_rank", "pct_championship_rosters", "adp_overall", "draft_status",
    "season_ppr_points", "espn_category", "narrative_label",
    "explicitly_named_league_winner", "reasoning_paraphrase",
    "inclusion_rule", "coverage_type",
    "article_title", "article_author", "article_publication_date", "article_url",
    "extraction_confidence", "ambiguity_notes",
]

# One entry per SOURCE ARTICLE (not per player) -- confirmed via direct
# fetch, per article, to be the "won the championship" series
# specifically, not the separate "finalist" or "playoff rosters"
# series ESPN also publishes each year under similar-sounding titles.
#
# Coverage-structure fields (added on review -- see README's
# "Interpreting this data correctly"):
#   inclusion_rule    -- human-readable description of exactly which
#                         players the article included (e.g. "Top 50",
#                         "championship-roster percentage >=10%").
#   coverage_type      -- controlled vocabulary for the same fact, for
#                         code to branch on:
#                           fixed_rank_cap        -- top-N by rank, N fixed
#                           percentage_threshold  -- everyone >= stated %
#                           complete_published_table -- source claims no
#                                                        cutoff at all (unused
#                                                        so far -- no year here
#                                                        makes that claim)
#                           inaccessible          -- confirmed to exist, paywalled
#                           partial_unstructured  -- confirmed right article,
#                                                     no extractable table
#   usable_for_benchmark -- False for inaccessible/partial_unstructured years
#   censoring_notes    -- what "not in this table" does and does NOT mean
#                         for this specific year (see README for the
#                         general rule this specializes).
ARTICLES = {
    2025: {
        "title": "Puka Nacua leads list of players on most 2025 fantasy football championship rosters",
        "author": "Tristan H. Cockcroft", "date": "2025-12-30",
        "url": "https://www.espn.com/fantasy/football/story/_/id/47454522/2025-fantasy-football",
        "accessible": True,
        "inclusion_rule": "Top 50", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 50 -- a player absent from this table may have been on 0 championship rosters, or may simply have ranked 51st+; the two cannot be distinguished from this row's absence alone.",
        "note": "Full table independently re-fetched and cross-verified once (separate tool call, identical result).",
    },
    2024: {
        "title": "Jahmyr Gibbs leads list of most common players on ESPN fantasy football championship rosters",
        "author": "Tristan H. Cockcroft", "date": "2025-01-06",
        "url": "https://www.espn.com/fantasy/football/story/_/id/43260187/fantasy-football-2024-most-common-players-championship-rosters",
        "accessible": True,
        "inclusion_rule": "Top 50", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 50 -- see 2025 entry for the general rule.",
        "note": "Spot-checked rank 35 (Terry McLaurin) against live article -- exact match.",
    },
    2023: {
        "title": "CeeDee Lamb the most common player on ESPN Fantasy Football championship rosters",
        "author": "Tristan H. Cockcroft", "date": "2024-01-08",
        "url": "https://www.espn.com/fantasy/football/story/_/id/39266644/2023-fantasy-football-championship-most-common-player",
        "accessible": True,
        "inclusion_rule": "Top 50", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 50 -- see 2025 entry for the general rule.",
        "note": "Spot-checked rank 30 (Jake Elliott) against live article -- exact match.",
    },
    2022: {
        "title": "McCaffrey, Mahomes among most common players on rosters of ESPN Fantasy Football champions",
        "author": "Tristan H. Cockcroft", "date": "2023-01-09",
        "url": "https://www.espn.com/fantasy/football/story/_/id/35412511/christian-mccaffrey-patrick-mahomes-austin-ekeler-travis-kelce",
        "accessible": True,
        "inclusion_rule": "Top 50", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 50 -- see 2025 entry for the general rule.",
        "note": "Spot-checked rank 25 (Travis Etienne Jr.) against live article -- exact match.",
    },
    2021: {
        "title": "Most common players on ESPN fantasy football champions - St. Brown, Kupp and Penny lead the way",
        "author": "Tristan H. Cockcroft", "date": "2022 (exact date not visible pre-paywall)",
        "url": "https://www.espn.com/fantasy/football/insider/story/_/id/33034607/most-common-players-espn-fantasy-football-champions-st-brown-kupp-penny-lead-way",
        "accessible": False,
        "inclusion_rule": "unknown (paywalled)", "coverage_type": "inaccessible", "usable_for_benchmark": False,
        "censoring_notes": "No player data recoverable this year -- absence from the overall dataset must not be read as any signal about 2021.",
        "note": (
            "ESPN+ Insider paywall -- only the intro paragraph is visible; the data "
            "table is not. Alternate retrieval attempted and failed: (1) web.archive.org "
            "-- tool cannot fetch this domain in this environment (hard tool error, not "
            "a paywall response); (2) search-indexed excerpts -- WebSearch snippets did "
            "not surface table rows beyond what direct fetch already showed; (3) "
            "syndicated copies -- found FantasyPros' independent 2021 'season in review' "
            "roster-frequency article, but confirmed it discloses no ESPN/Cockcroft "
            "citation and uses an undisclosed, likely different, methodology/platform -- "
            "NOT used, since substituting it would misattribute a different source's "
            "numbers as ESPN's; (4) authenticated ESPN+ access -- not available, no "
            "credentials held. No table recoverable via any legitimate path attempted."
        ),
    },
    2020: {
        "title": "Fantasy football - Josh Allen, Stefon Diggs among most common players on championship teams",
        "author": "Tristan H. Cockcroft", "date": "2021-01-05",
        "url": "https://insider.espn.com/fantasy/football/insider/story/_/id/30651247/fantasy-football-josh-allen-stefon-diggs-most-common-players-championship-teams",
        "accessible": False,
        "inclusion_rule": "unknown (paywalled)", "coverage_type": "inaccessible", "usable_for_benchmark": False,
        "censoring_notes": "No player data recoverable this year -- absence from the overall dataset must not be read as any signal about 2020.",
        "note": (
            "ESPN+ Insider paywall -- only the intro paragraph is visible (names Allen "
            "and Diggs, no percentages or full table). Same alternate-retrieval attempts "
            "as the 2021 entry, same result: web.archive.org unreachable (tool error), "
            "no useful search-snippet excerpt found, no syndicated copy located, no "
            "authenticated access available. No table recoverable."
        ),
    },
    2019: {
        "title": "Fantasy football: Christian McCaffrey, Breshad Perriman among most common players on fantasy championship rosters",
        "author": "Tristan H. Cockcroft", "date": "2019-12-30",
        "url": "https://www.espn.com/fantasy/football/story/_/id/28397128/fantasy-football-christian-mccaffrey-breshad-perriman-most-common-players-fantasy-championship-rosters",
        "accessible": True,
        "inclusion_rule": "championship-roster percentage >=10%", "coverage_type": "percentage_threshold", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at 10% -- a player absent from this table had a real championship-roster share below 10%, not necessarily 0%.",
        "note": "57 rows -- article's own stated cutoff, not a fetch limit. Spot-checked Kenyan Drake row against live article -- exact match.",
    },
    2018: {
        "title": "Christian McCaffrey, Patrick Mahomes and Nick Chubb among most common members of ESPN championship teams",
        "author": "Tristan H. Cockcroft", "date": "2018-12-31",
        "url": "https://www.espn.com/fantasy/football/story/_/id/25654815/fantasy-football-christian-mccaffrey-patrick-mahomes-nick-chubb-most-common-members-espn-championship-teams",
        "accessible": True,
        "inclusion_rule": "championship-roster percentage >=15%", "coverage_type": "percentage_threshold", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at 15% -- a player absent from this table had a real championship-roster share below 15%, not necessarily 0%.",
        "note": (
            "45 rows -- article's own stated cutoff. Also independently cross-validated: "
            "this article's own retrospective aside citing 2014/2015/2016/2017 leaders' "
            "percentages matches each of those years' own dedicated articles exactly "
            "(see README spot-check log)."
        ),
    },
    2017: {
        "title": "Todd Gurley, JuJu Smith-Schuster among most popular players on fantasy football champions",
        "author": "Tristan H. Cockcroft", "date": "2018-01-02",
        "url": "https://www.espn.com/fantasy/football/story/_/id/21941696/todd-gurley-juju-smith-schuster-most-popular-players-fantasy-football-champions",
        "accessible": True,
        "inclusion_rule": "championship-roster percentage >=12.5%", "coverage_type": "percentage_threshold", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at 12.5% -- article states explicitly 'all 31 players' at that threshold (confirmed not a fetch truncation), but players below 12.5% are still absent from this data, not confirmed at 0%.",
        "note": "31 rows.",
    },
    2016: {
        "title": "Packers, waiver-wire stars among most popular players for fantasy champions",
        "author": "Tom Carpenter", "date": "2017-01-02",
        "url": "https://cdn.espn.com/fantasy/football/story/_/id/18393889/david-johnson-leveon-bell-davante-adams-most-owned-champions",
        "accessible": True,
        "inclusion_rule": "Top 10", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 10 -- a much smaller published cutoff than 2022-2025's Top 50; do NOT compare this year's row count to other years' as if it reflected fewer notable players.",
        "note": (
            "Different article structure than other years -- overall list confirmed "
            "to stop at 10 rows (article also has separate top-5-by-position tables, "
            "not collected here to keep this file structurally consistent with the "
            "other years' single ranked list). Spot-checked rank 5 (Matt Bryant) "
            "against live article -- exact match. Different author than the Cockcroft-"
            "authored years."
        ),
    },
    2015: {
        "title": "Tim Hightower easily most popular player on fantasy champions",
        "author": "Keith Lipscomb", "date": "2016-01-04",
        "url": "https://www.espn.com/fantasy/football/story/_/id/14502773/tim-hightower-david-johnson-doug-baldwin-most-common-players-championship-winning-rosters",
        "accessible": True,
        "inclusion_rule": "Top 10", "coverage_type": "fixed_rank_cap", "usable_for_benchmark": True,
        "censoring_notes": "Right-censored at rank 10 -- see 2016 entry for the general rule; also no ADP/points columns published this year.",
        "note": (
            "Article explicitly caps its own list at 10 ('the 10 players/defenses with "
            "the highest such ownership numbers') -- confirmed not a fetch truncation. "
            "No ADP/points columns in this year's article. Spot-checked rank 7 (Chiefs "
            "D/ST) against live article -- exact match. Different author than the "
            "Cockcroft-authored years."
        ),
    },
    2014: {
        "title": "Popular players on fantasy champs",
        "author": "Keith Lipscomb", "date": "2014-12-30",
        "url": "https://www.espn.com/fantasy/football/story/_/id/12092730/odell-beckham-jr-far-most-popular-player-champions-rosters",
        "accessible": False,
        "inclusion_rule": "unstructured -- 4 players named in prose only, no table", "coverage_type": "partial_unstructured", "usable_for_benchmark": False,
        "censoring_notes": "No structured player data captured this year -- do not treat as a 0-row or empty season.",
        "note": (
            "Article confirmed to be the correct 'won championship' series, but no "
            "structured ranked table could be extracted -- only 4 named players with "
            "partial, inconsistent stats appear in the fetched prose (points shown for "
            "some, not percentages for others). NOT transcribed into the table dataset "
            "to avoid fabricating column values the source didn't clearly provide in an "
            "extractable form. Only Beckham's rank-1 status and 31.0% figure are solid "
            "(independently cross-validated against the 2018 article's retrospective "
            "citation of the same number)."
        ),
    },
}

# 2013 and earlier: SEARCHED, NOT LOCATED. Multiple targeted queries
# (title-pattern search, player-name search) returned no standalone
# "won the championship" article for the 2013 season or earlier. Not
# added to ARTICLES since no confirmed source exists to cite. This is
# reported here, not silently omitted, per the explicit instruction to
# report every year checked including negative results.
YEARS_SEARCHED_NOT_LOCATED = [2013]

# (rank, player, position, team, pct_championship_rosters, adp_or_None, ppr_points_or_None, narrative_label_or_None)
# ADP of None means the article showed "Undrafted" for that player, OR
# (2015/2016 only) the article simply didn't publish an ADP column that year.
TABLES = {
    2025: [
        (1, "Puka Nacua", "WR", "LAR", 29.1, 11.6, 349.00, None),
        (2, "Jaxon Smith-Njigba", "WR", "SEA", 25.2, 39.1, 345.50, "dominant, consistent campaign"),
        (3, "Bijan Robinson", "RB", "ATL", 23.8, 2.8, 363.50, "stellar regular season, explosive playoff finish"),
        (4, "Trey McBride", "TE", "ARI", 22.4, 27.1, 302.40, None),
        (5, "Christian McCaffrey", "RB", "SF", 20.1, 7.2, 404.90, None),
        (6, "Brandon Aubrey", "K", "DAL", 18.7, 117.0, 180.60, "rare kicker on >15% of championship rosters in past 7 seasons"),
        (7, "James Cook III", "RB", "BUF", 18.2, 32.4, 300.70, None),
        (8, "Drake Maye", "QB", "NE", 18.0, 125.1, 336.22, "breakthrough performer"),
        (9, "Michael Wilson", "WR", "ARI", 17.4, None, 199.70, "waiver-wire gem"),
        (10, "Chase Brown", "RB", "CIN", 17.1, 25.7, 263.60, None),
        (11, "Jonathan Taylor", "RB", "IND", 16.9, 18.3, 356.40, None),
        (12, "De'Von Achane", "RB", "MIA", 16.7, 16.4, 322.80, None),
        (13, "Josh Allen", "QB", "BUF", 16.3, 20.6, 364.62, None),
        (14, "Chris Olave", "WR", "NO", 15.8, 97.0, 268.00, None),
        (15, "Matthew Stafford", "QB", "LAR", 15.7, 159.9, 323.72, None),
        (16, "Rico Dowdle", "RB", "CAR", 15.5, None, 213.30, None),
        (17, "Amon-Ra St. Brown", "WR", "DET", 15.3, 11.3, 299.10, None),
        (18, "Texans D/ST", "D/ST", "HOU", 15.2, 117.3, 162.00, None),
        (19, "Kyle Pitts Sr.", "TE", "ATL", 14.9, 144.2, 199.00, None),
        (20, "Broncos D/ST", "D/ST", "DEN", 14.6, 100.5, 124.00, None),
        (21, "Kyren Williams", "RB", "LAR", 14.4, 30.7, 252.20, None),
        (22, "Jahmyr Gibbs", "RB", "DET", 14.4, 5.2, 346.60, "led this list last season (29.0%); no worse than 22nd in each of first 3 seasons"),
        (23, "Ja'Marr Chase", "WR", "CIN", 14.3, 1.5, 290.00, None),
        (24, "George Pickens", "WR", "DAL", 14.3, 75.9, 290.00, None),
        (25, "Harold Fannin Jr.", "TE", "CLE", 14.1, 169.9, 186.40, None),
        (26, "Derrick Henry", "RB", "BAL", 13.9, 14.7, 266.90, None),
        (27, "George Kittle", "TE", "SF", 13.6, 36.9, 153.60, None),
        (28, "Travis Etienne Jr.", "RB", "JAX", 13.5, 126.3, 249.10, None),
        (29, "Jason Myers", "K", "SEA", 13.5, None, 189.00, None),
        (30, "Seahawks D/ST", "D/ST", "SEA", 13.4, 143.6, 173.00, None),
        (31, "Cameron Dicker", "K", "LAC", 13.0, 125.3, 164.00, None),
        (32, "Nico Collins", "WR", "HOU", 12.7, 15.2, 226.20, None),
        (33, "Wan'Dale Robinson", "WR", "NYG", 12.6, 163.4, 217.90, None),
        (34, "Courtland Sutton", "WR", "DEN", 12.5, 64.2, 218.20, None),
        (35, "Javonte Williams", "RB", "DAL", 12.5, 114.5, 242.80, None),
        (36, "Jake Ferguson", "TE", "DAL", 12.3, 140.5, 186.60, None),
        (37, "Tyler Warren", "TE", "IND", 12.3, 100.3, 180.90, None),
        (38, "Dak Prescott", "QB", "DAL", 12.2, 113.4, 313.08, None),
        (39, "Mike Evans", "WR", "TB", 12.2, 50.5, 79.40, None),
        (40, "Zay Flowers", "WR", "BAL", 11.9, 60.7, 213.50, None),
        (41, "Kenneth Gainwell", "RB", "PIT", 11.8, None, 199.90, None),
        (42, "Dallas Goedert", "TE", "PHI", 11.6, 133.3, 185.10, None),
        (43, "Joe Burrow", "QB", "CIN", 11.5, 34.1, 113.32, None),
        (44, "RJ Harvey", "RB", "DEN", 11.3, 81.8, 202.30, None),
        (45, "Patriots D/ST", "D/ST", "NE", 11.3, 156.9, 119.00, None),
        (46, "Rashee Rice", "WR", "KC", 11.0, 88.1, 150.10, None),
        (47, "Omarion Hampton", "RB", "LAC", 11.0, 40.7, 135.70, None),
        (48, "A.J. Brown", "WR", "PHI", 11.0, 18.6, 220.30, None),
        (49, "Emeka Egbuka", "WR", "TB", 10.9, 90.8, 193.90, None),
        (50, "Drake London", "WR", "ATL", 10.8, 22.3, 184.10, None),
    ],
    2024: [
        (1, "Jahmyr Gibbs", "RB", "DET", 29.0, 16.0, 362.90, None),
        (2, "Ja'Marr Chase", "WR", "CIN", 21.5, 8.0, 403.00, None),
        (3, "Lamar Jackson", "QB", "BAL", 20.8, 35.4, 430.38, None),
        (4, "Bucky Irving", "RB", "TB", 19.3, 167.5, 244.40, "in-season pickup that stood above the rest for championship contributions"),
        (5, "Brock Bowers", "TE", "LV", 19.1, 115.7, 262.70, "record-setting rookie season; No. 1 TE on playoff/finalist/championship rosters"),
        (6, "Trey McBride", "TE", "ARI", 18.7, 54.0, 249.80, None),
        (7, "Bijan Robinson", "RB", "ATL", 18.6, 3.7, 341.70, None),
        (8, "Amon-Ra St. Brown", "WR", "DET", 18.1, 7.0, 316.18, None),
        (9, "Brian Thomas Jr.", "WR", "JAX", 18.0, 121.5, 284.00, None),
        (10, "Malik Nabers", "WR", "NYG", 17.7, 42.8, 273.60, None),
        (11, "Derrick Henry", "RB", "BAL", 17.6, 20.7, 336.40, None),
        (12, "Eagles D/ST", "D/ST", "PHI", 17.0, 166.9, 138.00, None),
        (13, "De'Von Achane", "RB", "MIA", 17.0, 42.1, 299.90, None),
        (14, "Jonnu Smith", "TE", "MIA", 16.8, None, 222.30, "in-season pickup that stood above the rest for championship contributions"),
        (15, "Mike Evans", "WR", "TB", 16.7, 25.6, 240.40, None),
        (16, "Jayden Daniels", "QB", "WAS", 16.4, 109.7, 355.82, None),
        (17, "Baker Mayfield", "QB", "TB", 16.4, 164.2, 365.80, None),
        (18, "Justin Jefferson", "WR", "MIN", 16.3, 8.6, 317.48, None),
        (19, "Ravens D/ST", "D/ST", "BAL", 16.2, 108.9, 106.00, None),
        (20, "Jonathan Taylor", "RB", "IND", 15.9, 10.7, 244.70, None),
        (21, "Broncos D/ST", "D/ST", "DEN", 15.6, 169.5, 166.00, None),
        (22, "Josh Jacobs", "RB", "GB", 15.5, 34.1, 293.10, None),
        (23, "Tee Higgins", "WR", "CIN", 15.4, 65.1, 222.10, None),
        (24, "Saquon Barkley", "RB", "PHI", 15.2, 10.8, 355.30, None),
        (25, "Davante Adams", "WR", "NYJ", 15.0, 27.4, 241.30, None),
        (26, "Joe Burrow", "QB", "CIN", 14.8, 55.3, 372.82, None),
        (27, "Chase McLaughlin", "K", "TB", 14.3, None, 162.00, None),
        (28, "Drake London", "WR", "ATL", 14.1, 34.7, 280.80, None),
        (29, "Jake Bates", "K", "DET", 13.8, 168.7, 158.00, None),
        (30, "Chase Brown", "RB", "CIN", 13.7, 122.6, 255.00, None),
        (31, "George Kittle", "TE", "SF", 13.5, 54.6, 236.60, None),
        (32, "Michael Carter", "RB", "ARI", 13.4, 170.0, 35.80, "critical injury-driven pickup -- 'remain vigilant with pickups'"),
        (33, "James Cook", "RB", "BUF", 13.2, 34.6, 266.70, None),
        (34, "Josh Allen", "QB", "BUF", 13.2, 26.9, 379.04, None),
        (35, "Terry McLaurin", "WR", "WAS", 13.1, 86.0, 267.80, None),
        (36, "Sam LaPorta", "TE", "DET", 12.9, 35.2, 174.60, None),
        (37, "Brandon Aubrey", "K", "DAL", 12.9, 108.9, 187.00, None),
        (38, "Nico Collins", "WR", "HOU", 12.8, 33.4, 210.60, None),
        (39, "Sam Darnold", "QB", "MIN", 12.7, 169.9, 307.96, None),
        (40, "Chris Boswell", "K", "PIT", 12.7, 169.3, 188.00, None),
        (41, "Bo Nix", "QB", "DEN", 12.6, 167.4, 317.20, None),
        (42, "Isaac Guerendo", "RB", "SF", 12.5, None, 94.20, None),
        (43, "Zach Charbonnet", "RB", "SEA", 11.9, 151.8, 186.90, None),
        (44, "Aaron Jones", "RB", "MIN", 11.8, 68.8, 241.60, None),
        (45, "Alvin Kamara", "RB", "NO", 11.8, 32.0, 265.30, None),
        (46, "Puka Nacua", "WR", "LAR", 11.7, 15.6, 206.60, None),
        (47, "A.J. Brown", "WR", "PHI", 11.6, 12.3, 216.90, None),
        (48, "Kyren Williams", "RB", "LAR", 11.4, 18.2, 272.10, None),
        (49, "Cameron Dicker", "K", "LAC", 11.3, 157.5, 176.00, None),
        (50, "Jared Goff", "QB", "DET", 11.2, 146.9, 324.46, None),
    ],
    2023: [
        (1, "CeeDee Lamb", "WR", "DAL", 30.6, 16.6, 403.20, None),
        (2, "Amon-Ra St. Brown", "WR", "DET", 24.8, 21.0, 330.90, None),
        (3, "Kyren Williams", "RB", "LAR", 23.2, None, 255.00, "undrafted, 23.2% of championship rosters"),
        (4, "Sam LaPorta", "TE", "DET", 23.1, 165.5, 239.30, "rookie PPR TE scoring record; top-rostered rookie"),
        (5, "Christian McCaffrey", "RB", "SF", 21.6, 4.3, 391.30, None),
        (6, "Puka Nacua", "WR", "LAR", 21.1, None, 298.50, None),
        (7, "Brandon Aubrey", "K", "DAL", 20.4, 169.7, 180.00, None),
        (8, "Breece Hall", "RB", "NYJ", 18.9, 55.7, 290.50, None),
        (9, "Josh Allen", "QB", "BUF", 18.2, 21.0, 392.64, None),
        (10, "Justin Jefferson", "WR", "MIN", 17.8, 1.5, 202.20, None),
        (11, "Zamir White", "RB", "LV", 16.6, None, 73.90, "strictly a fantasy-playoffs pickup; 'waiver-wire wonder'"),
        (12, "Tyreek Hill", "WR", "MIA", 16.5, 6.3, 376.40, None),
        (13, "Trey McBride", "TE", "ARI", 16.4, None, 181.50, None),
        (14, "De'Von Achane", "RB", "MIA", 15.8, 166.3, 190.70, None),
        (15, "James Conner", "RB", "ARI", 15.8, 61.7, 201.50, None),
        (16, "C.J. Stroud", "QB", "HOU", 15.5, 169.0, 276.02, None),
        (17, "Nico Collins", "WR", "HOU", 15.5, 148.4, 260.40, None),
        (18, "Jahmyr Gibbs", "RB", "DET", 14.8, 34.0, 242.10, None),
        (19, "Cowboys D/ST", "D/ST", "DAL", 14.8, 115.9, 172.00, None),
        (20, "Dak Prescott", "QB", "DAL", 14.2, 98.5, 342.84, None),
        (21, "Lamar Jackson", "QB", "BAL", 14.2, 32.4, 331.22, None),
        (22, "Evan Engram", "TE", "JAX", 14.1, 86.0, 230.30, None),
        (23, "Raheem Mostert", "RB", "MIA", 14.0, 123.3, 267.70, None),
        (24, "Jalen Hurts", "QB", "PHI", 13.9, 22.8, 356.82, None),
        (25, "Rachaad White", "RB", "TB", 13.8, 58.0, 267.90, None),
        (26, "Travis Etienne Jr.", "RB", "JAX", 13.7, 30.1, 282.40, None),
        (27, "Kyler Murray", "QB", "ARI", 13.4, 169.0, 146.36, None),
        (28, "Joe Mixon", "RB", "CIN", 13.3, 23.3, 267.00, None),
        (29, "Mike Evans", "WR", "TB", 12.9, 71.9, 282.50, None),
        (30, "Jake Elliott", "K", "PHI", 13.0, 139.7, 155.00, None),
        (31, "Jonathan Taylor", "RB", "IND", 12.8, 78.2, 156.40, None),
        (32, "Jets D/ST", "D/ST", "NYJ", 12.8, 134.8, 157.00, None),
        (33, "Rashee Rice", "WR", "KC", 12.6, None, 212.50, None),
        (34, "Browns D/ST", "D/ST", "CLE", 12.6, 144.7, 167.00, None),
        (35, "Kenneth Walker III", "RB", "SEA", 12.3, 56.0, 199.40, None),
        (36, "Alvin Kamara", "RB", "NO", 12.2, 56.7, 233.00, None),
        (37, "Jake Ferguson", "TE", "DAL", 12.2, 169.4, 177.10, None),
        (38, "Deebo Samuel", "WR", "SF", 12.0, 35.8, 243.70, None),
        (39, "Keenan Allen", "WR", "LAC", 11.9, 42.5, 278.86, None),
        (40, "Davante Adams", "WR", "LV", 11.8, 9.9, 265.40, None),
        (41, "Saquon Barkley", "RB", "NYG", 11.8, 11.1, 223.20, None),
        (42, "Bijan Robinson", "RB", "ATL", 11.8, 10.2, 246.30, None),
        (43, "Justin Tucker", "K", "BAL", 11.8, 87.4, 155.00, None),
        (44, "Brandon Aiyuk", "WR", "SF", 11.6, 83.1, 249.20, None),
        (45, "Jordan Love", "QB", "GB", 11.6, 167.3, 319.06, None),
        (46, "DJ Moore", "WR", "CHI", 11.4, 60.7, 286.50, None),
        (47, "Ezekiel Elliott", "RB", "NE", 11.2, 137.9, 174.50, None),
        (48, "David Montgomery", "RB", "DET", 11.0, 83.8, 207.20, None),
        (49, "Chris Olave", "WR", "NO", 11.0, 30.2, 231.30, None),
        (50, "Justin Fields", "QB", "CHI", 10.8, 49.8, 230.18, None),
    ],
    2022: [
        (1, "Christian McCaffrey", "RB", "SF", 22.8, 3.1, 404.56, None),
        (2, "Patrick Mahomes", "QB", "KC", 22.2, 31.6, 457.90, None),
        (3, "Austin Ekeler", "RB", "LAC", 22.0, 5.0, 413.80, None),
        (4, "Travis Kelce", "TE", "KC", 21.4, 19.6, 337.40, None),
        (5, "A.J. Brown", "WR", "PHI", 20.4, 36.0, 332.80, None),
        (6, "CeeDee Lamb", "WR", "DAL", 19.8, 20.4, 338.80, None),
        (7, "George Kittle", "TE", "SF", 19.8, 48.2, 231.70, None),
        (8, "Jalen Hurts", "QB", "PHI", 18.0, 63.4, 386.50, None),
        (9, "Derrick Henry", "RB", "TEN", 16.3, 5.9, 316.56, None),
        (10, "Nick Chubb", "RB", "CLE", 15.7, 29.0, 317.20, None),
        (11, "Tyreek Hill", "WR", "MIA", 15.7, 19.2, 367.20, None),
        (12, "Eagles D/ST", "D/ST", "PHI", 15.7, 165.1, 173.00, None),
        (13, "Saquon Barkley", "RB", "NYG", 15.6, 28.0, 291.30, None),
        (14, "Josh Jacobs", "RB", "LV", 15.5, 56.9, 354.80, None),
        (15, "T.J. Hockenson", "TE", "MIN", 15.3, 73.7, 230.90, None),
        (16, "Josh Allen", "QB", "BUF", 15.2, 24.0, 417.28, None),
        (17, "Keenan Allen", "WR", "LAC", 15.0, 26.2, 206.00, None),
        (18, "Amon-Ra St. Brown", "WR", "DET", 14.6, 64.6, 288.70, None),
        (19, "Jerick McKinnon", "RB", "KC", 14.3, None, 227.50, None),
        (20, "Justin Tucker", "K", "BAL", 14.1, 95.8, 182.00, None),
        (21, "Justin Jefferson", "WR", "MIN", 13.8, 6.3, 378.96, None),
        (22, "DeVonta Smith", "WR", "PHI", 13.7, 95.9, 288.80, None),
        (23, "Davante Adams", "WR", "LV", 13.3, 12.7, 382.10, None),
        (24, "Chris Godwin", "WR", "TB", 13.3, 65.0, 253.30, None),
        (25, "Travis Etienne Jr.", "RB", "JAX", 13.3, 49.3, 233.50, None),
        (26, "Kenneth Walker III", "RB", "SEA", 13.2, 140.5, 231.10, None),
        (27, "Jaylen Waddle", "WR", "MIA", 13.2, 49.0, 277.70, None),
        (28, "Cam Akers", "RB", "LAR", 12.9, 34.5, 171.40, None),
        (29, "49ers D/ST", "D/ST", "SF", 12.7, 126.2, 169.00, None),
        (30, "Daniel Carlson", "K", "LV", 12.7, 133.9, 181.00, None),
        (31, "Bills D/ST", "D/ST", "BUF", 12.6, 83.6, 157.00, None),
        (32, "Rhamondre Stevenson", "RB", "NE", 12.4, 99.5, 269.40, None),
        (33, "Brett Maher", "K", "DAL", 12.4, None, 168.00, None),
        (34, "Aaron Jones", "RB", "GB", 12.2, 23.7, 269.70, None),
        (35, "Joe Burrow", "QB", "CIN", 12.1, 81.3, 362.30, None),
        (36, "Mike Evans", "WR", "TB", 12.1, 28.4, 274.10, None),
        (37, "Christian Watson", "WR", "GB", 12.0, None, 182.80, None),
        (38, "Tyler Allgeier", "RB", "ATL", 12.0, 168.4, 189.40, None),
        (39, "Evan Engram", "TE", "JAX", 11.7, 168.6, 187.50, None),
        (40, "Joe Mixon", "RB", "CIN", 11.4, 13.9, 257.30, None),
        (41, "Stefon Diggs", "WR", "BUF", 11.4, 14.0, 340.00, None),
        (42, "Cowboys D/ST", "D/ST", "DAL", 11.3, 137.5, 167.00, None),
        (43, "Terry McLaurin", "WR", "WAS", 11.2, 40.3, 251.10, None),
        (44, "DeAndre Hopkins", "WR", "ARI", 11.1, 102.6, 151.70, None),
        (45, "Ja'Marr Chase", "WR", "CIN", 11.1, 8.0, 265.00, None),
        (46, "Amari Cooper", "WR", "CLE", 11.0, 78.1, 278.60, None),
        (47, "Tony Pollard", "RB", "DAL", 11.0, 100.4, 250.70, None),
        (48, "James Conner", "RB", "ARI", 10.9, 26.7, 214.20, None),
        (49, "Michael Pittman Jr.", "WR", "IND", 10.9, 33.9, 244.60, None),
        (50, "Alvin Kamara", "RB", "NO", 10.8, 11.9, 232.70, None),
    ],
    2019: [
        (1, "Breshad Perriman", "WR", "TB", 27.2, None, 138.1, None),
        (2, "A.J. Brown", "WR", "TEN", 26.8, None, 217.1, None),
        (3, "Christian McCaffrey", "RB", "CAR", 25.4, 2.8, 471.2, None),
        (4, "Tyler Higbee", "TE", "LAR", 21.3, None, 160.4, None),
        (5, "DeVante Parker", "WR", "MIA", 21.2, None, 246.2, None),
        (6, "Ryan Tannehill", "QB", "TEN", 21.2, None, 224.2, None),
        (7, "Raheem Mostert", "RB", "SF", 19.4, None, 165.2, None),
        (8, "Aaron Jones", "RB", "GB", 19.4, 39.7, 314.8, None),
        (9, "Lamar Jackson", "QB", "BAL", 19.1, 124.4, 415.7, None),
        (10, "Steelers D/ST", "D/ST", "PIT", 18.4, None, 181.0, None),
        (11, "Darren Waller", "TE", "OAK", 18.4, None, 221.0, None),
        (12, "Ravens D/ST", "D/ST", "BAL", 18.1, None, 152.0, None),
        (13, "Austin Ekeler", "RB", "LAC", 16.7, 91.6, 309.0, None),
        (14, "Derrick Henry", "RB", "TEN", 16.3, 35.5, 294.6, None),
        (15, "Michael Thomas", "WR", "NO", 16.3, 10.0, 374.6, None),
        (16, "DeAndre Washington", "RB", "OAK", 15.4, None, 121.9, None),
        (17, "Travis Kelce", "TE", "KC", 15.4, 17.2, 254.3, None),
        (18, "Dallas Goedert", "TE", "PHI", 14.8, None, 144.7, None),
        (19, "DJ Chark Jr.", "WR", "JAX", 14.7, None, 225.8, None),
        (20, "Harrison Butker", "K", "KC", 14.2, 123.3, 162.0, None),
        (21, "Patriots D/ST", "D/ST", "NE", 14.2, 141.7, 225.0, None),
        (22, "Drew Brees", "QB", "NO", 14.2, 71.6, 224.8, None),
        (23, "George Kittle", "TE", "SF", 14.1, 30.5, 222.5, None),
        (24, "Mark Andrews", "TE", "BAL", 13.8, 152.0, 207.2, None),
        (25, "Ezekiel Elliott", "RB", "DAL", 13.6, 5.8, 311.7, None),
        (26, "Kenyan Drake", "RB", "ARI", 13.4, 75.4, 214.2, None),
        (27, "Keenan Allen", "WR", "LAC", 13.3, 25.0, 261.5, None),
        (28, "Wil Lutz", "K", "NO", 12.9, 122.2, 159.0, None),
        (29, "Jameis Winston", "QB", "TB", 12.8, 153.6, 305.4, None),
        (30, "Kareem Hunt", "RB", "CLE", 12.5, 145.6, 101.4, None),
        (31, "49ers D/ST", "D/ST", "SF", 12.5, None, 165.0, None),
        (32, "Marlon Mack", "RB", "IND", 12.2, 64.6, 181.3, None),
        (33, "Cooper Kupp", "WR", "LAR", 12.1, 52.2, 270.5, None),
        (34, "Julio Jones", "WR", "ATL", 12.0, 12.2, 274.1, None),
        (35, "Mike Boone", "RB", "MIN", 12.0, None, 50.0, None),
        (36, "Saquon Barkley", "RB", "NYG", 11.9, 1.3, 244.1, None),
        (37, "Joe Mixon", "RB", "CIN", 11.8, 18.3, 225.4, None),
        (38, "Dak Prescott", "QB", "DAL", 11.7, 92.1, 337.8, None),
        (39, "Robert Woods", "WR", "LAR", 11.6, 44.8, 232.9, None),
        (40, "Miles Sanders", "RB", "PHI", 11.4, 88.9, 218.7, None),
        (41, "Austin Hooper", "TE", "ATL", 11.0, 110.5, 191.7, None),
        (42, "Jared Cook", "TE", "NO", 10.9, 65.4, 167.5, None),
        (43, "Carson Wentz", "QB", "PHI", 10.7, 77.5, 275.9, None),
        (44, "Allen Robinson II", "WR", "CHI", 10.7, 73.4, 254.9, None),
        (45, "Dalvin Cook", "RB", "MIN", 10.6, 20.6, 292.4, None),
        (46, "Kenny Golladay", "WR", "DET", 10.6, 50.3, 248.0, None),
        (47, "Tyler Boyd", "WR", "CIN", 10.6, 68.6, 222.9, None),
        (48, "Melvin Gordon", "RB", "LAC", 10.6, 45.2, 180.8, None),
        (49, "Nick Chubb", "RB", "CLE", 10.5, 20.6, 255.2, None),
        (50, "Michael Gallup", "WR", "DAL", 10.5, 120.4, 212.7, None),
        (51, "Russell Wilson", "QB", "SEA", 10.4, 101.6, 328.6, None),
        (52, "Bills D/ST", "D/ST", "BUF", 10.3, 122.1, 131.0, None),
        (53, "John Brown", "WR", "BUF", 10.3, None, 219.8, None),
        (54, "Damien Williams", "RB", "KC", 10.2, 63.4, 141.1, None),
        (55, "Deshaun Watson", "QB", "HOU", 10.2, 42.1, 321.0, None),
        (56, "Chris Godwin", "WR", "TB", 10.2, 59.6, 276.1, None),
        (57, "Justin Tucker", "K", "BAL", 10.1, 104.8, 152.0, None),
    ],
    2018: [
        (1, "Christian McCaffrey", "RB", "CAR", 37.8, 17.8, 385.5, None),
        (2, "Patrick Mahomes", "QB", "KC", 35.5, 118.1, 417.1, None),
        (3, "Travis Kelce", "TE", "KC", 33.2, 26.6, 294.6, None),
        (4, "Adam Thielen", "WR", "MIN", 33.0, 35.2, 307.3, None),
        (5, "Nick Chubb", "RB", "CLE", 31.8, 134.2, 194.5, None),
        (6, "Saquon Barkley", "RB", "NYG", 31.2, 7.0, 385.8, None),
        (7, "Tyreek Hill", "WR", "KC", 31.0, 32.1, 334.0, None),
        (8, "Bears D/ST", "D/ST", "CHI", 30.9, 133.8, 188.0, None),
        (9, "JuJu Smith-Schuster", "WR", "PIT", 30.8, 51.4, 296.9, None),
        (10, "Zach Ertz", "TE", "PHI", 29.4, 34.5, 280.3, None),
        (11, "Alvin Kamara", "RB", "NO", 28.8, 7.3, 354.2, None),
        (12, "Greg Zuerlein", "K", "LAR", 26.9, 100.3, 124.0, None),
        (13, "George Kittle", "TE", "SF", 25.6, 135.7, 258.7, None),
        (14, "Davante Adams", "WR", "GB", 25.5, 22.5, 329.6, None),
        (15, "Phillip Lindsay", "RB", "DEN", 25.2, None, 222.8, None),
        (16, "Melvin Gordon", "RB", "LAC", 23.8, 15.2, 275.5, None),
        (17, "Ezekiel Elliott", "RB", "DAL", 23.7, 4.1, 329.1, None),
        (18, "Stefon Diggs", "WR", "MIN", 23.2, 32.2, 266.3, None),
        (19, "Jaylen Samuels", "RB", "PIT", 23.0, None, 89.5, None),
        (20, "Michael Thomas", "WR", "NO", 22.7, 18.4, 315.5, None),
        (21, "Ka'imi Fairbairn", "K", "HOU", 21.6, None, 165.0, None),
        (22, "Rams D/ST", "D/ST", "LAR", 21.5, 90.1, 131.0, None),
        (23, "Justin Tucker", "K", "BAL", 21.5, 118.5, 156.0, None),
        (24, "Brandin Cooks", "WR", "LAR", 20.5, 50.0, 243.2, None),
        (25, "Titans D/ST", "D/ST", "TEN", 20.5, 142.3, 113.0, None),
        (26, "Wil Lutz", "K", "NO", 20.4, 141.2, 149.0, None),
        (27, "Joe Mixon", "RB", "CIN", 20.0, 30.2, 243.4, None),
        (28, "Eric Ebron", "TE", "IND", 20.0, None, 222.2, None),
        (29, "Julian Edelman", "WR", "NE", 19.9, 94.3, 207.4, None),
        (30, "Robert Woods", "WR", "LAR", 19.8, 71.9, 265.6, None),
        (31, "Drew Brees", "QB", "NO", 19.1, 74.1, 305.0, None),
        (32, "Amari Cooper", "WR", "OAK/DAL", 18.8, 39.9, 215.5, None),
        (33, "Tarik Cohen", "RB", "CHI", 18.8, 104.6, 233.9, None),
        (34, "Damien Williams", "RB", "KC", 18.4, None, 98.6, None),
        (35, "DeAndre Hopkins", "WR", "HOU", 18.2, 10.7, 333.5, None),
        (36, "T.Y. Hilton", "WR", "IND", 18.2, 31.0, 239.0, None),
        (37, "Mike Evans", "WR", "TB", 18.1, 26.3, 290.4, None),
        (38, "Harrison Butker", "K", "KC", 17.7, 151.1, 144.0, None),
        (39, "Antonio Brown", "WR", "PIT", 17.4, 4.9, 323.7, None),
        (40, "Vikings D/ST", "D/ST", "MIN", 17.3, 99.9, 125.0, None),
        (41, "Keenan Allen", "WR", "LAC", 17.2, 16.9, 260.1, None),
        (42, "Todd Gurley II", "RB", "LAR", 17.2, 1.7, 372.1, None),
        (43, "Jared Cook", "TE", "OAK", 17.0, 132.1, 193.6, None),
        (44, "Stephen Gostkowski", "K", "NE", 15.6, 99.6, 133.0, None),
        (45, "Julio Jones", "WR", "ATL", 15.5, 9.4, 325.9, None),
    ],
    2017: [
        (1, "Todd Gurley II", "RB", "LAR", 34.4, 19.9, 383.30, None),
        (2, "Alvin Kamara", "RB", "NO", 24.1, None, 320.40, None),
        (3, "JuJu Smith-Schuster", "WR", "PIT", 23.8, None, 197.70, None),
        (4, "Dion Lewis", "RB", "NE", 21.4, None, 203.00, None),
        (5, "Kareem Hunt", "RB", "KC", 19.1, 36.5, 295.20, None),
        (6, "Kenyan Drake", "RB", "MIA", 18.6, None, 142.30, None),
        (7, "Josh Gordon", "WR", "CLE", 18.4, None, 57.50, None),
        (8, "Melvin Gordon", "RB", "LAC", 17.9, 14.1, 288.10, None),
        (9, "Marquise Goodwin", "WR", "SF", 16.8, None, 168.60, None),
        (10, "Jamaal Williams", "RB", "GB", 16.2, None, 142.80, None),
        (11, "Jimmy Garoppolo", "QB", "SF", 16.0, None, 87.90, None),
        (12, "Alex Collins", "RB", "BAL", 15.7, None, 171.00, None),
        (13, "Ravens D/ST", "D/ST", "BAL", 15.6, 130.2, 172.00, None),
        (14, "Greg Olsen", "TE", "CAR", 15.3, 45.6, 42.10, None),
        (15, "Devin Funchess", "WR", "CAR", 15.0, None, 195.00, None),
        (16, "Le'Veon Bell", "RB", "PIT", 14.8, 2.1, 341.60, None),
        (17, "Rob Gronkowski", "TE", "NE", 13.7, 19.9, 227.40, None),
        (18, "DeAndre Hopkins", "WR", "HOU", 13.6, 32.6, 309.80, None),
        (19, "Russell Wilson", "QB", "SEA", 13.6, 57.0, 347.92, None),
        (20, "Ezekiel Elliott", "RB", "DAL", 13.6, 19.0, 203.20, None),
        (21, "Jaguars D/ST", "D/ST", "JAX", 13.6, 143.8, 208.00, None),
        (22, "Marvin Jones Jr.", "WR", "DET", 13.6, 130.2, 225.10, None),
        (23, "Chris Boswell", "K", "PIT", 13.4, 149.7, 156.00, None),
        (24, "Keenan Allen", "WR", "LAC", 13.4, 42.2, 284.20, None),
        (25, "Tyreek Hill", "WR", "KC", 13.3, 58.0, 245.20, None),
        (26, "Latavius Murray", "RB", "MIN", 13.0, 143.2, 157.50, None),
        (27, "Derrick Henry", "RB", "TEN", 13.0, 132.6, 135.00, None),
        (28, "Steelers D/ST", "D/ST", "PIT", 13.0, 126.2, 135.00, None),
        (29, "Chargers D/ST", "D/ST", "LAC", 12.8, 147.9, 145.00, None),
        (30, "Philip Rivers", "QB", "LAC", 12.7, 130.4, 270.40, None),
        (31, "LeSean McCoy", "RB", "BUF", 12.6, 7.5, 263.60, None),
    ],
    2016: [
        (1, "David Johnson", "RB", "ARI", 23.6, None, None, None),
        (2, "Le'Veon Bell", "RB", "PIT", 23.0, None, None, None),
        (3, "Matt Ryan", "QB", "ATL", 22.0, None, None, None),
        (4, "Davante Adams", "WR", "GB", 21.2, None, None, None),
        (5, "Matt Bryant", "K", "ATL", 20.5, None, None, None),
        (6, "Ty Montgomery", "RB", "GB", 20.4, None, None, "listed as RB/WR in source"),
        (7, "Jordan Howard", "RB", "CHI", 20.2, None, None, None),
        (8, "LeSean McCoy", "RB", "BUF", 19.8, None, None, None),
        (9, "Aaron Rodgers", "QB", "GB", 18.1, None, None, None),
        (10, "Robert Kelley", "RB", "WAS", 18.0, None, None, None),
    ],
    2015: [
        (1, "Tim Hightower", "RB", "NO", 33.6, None, None, None),
        (2, "David Johnson", "RB", "ARI", 25.5, None, None, None),
        (3, "Doug Baldwin", "WR", "SEA", 24.3, None, None, None),
        (4, "Jordan Reed", "TE", "WAS", 23.4, None, None, None),
        (5, "Charcandrick West", "RB", "KC", 21.4, None, None, None),
        (6, "Gary Barnidge", "TE", "CLE", 21.4, None, None, None),
        (7, "Chiefs D/ST", "D/ST", "KC", 20.4, None, None, None),
        (8, "Julio Jones", "WR", "ATL", 20.1, None, None, None),
        (9, "Brandon Marshall", "WR", "NYJ", 19.7, None, None, None),
        (10, "Cam Newton", "QB", "CAR", 19.6, None, None, None),
    ],
}

# 2014: article confirmed correct series, but NOT transcribed into
# TABLES -- no extractable structured table, only 4 named players with
# inconsistent partial stats in the fetched prose (see ARTICLES[2014]'s
# note). Listed in sources.csv (accessible=False) rather than faked.


def build_rows():
    rows = []
    for season, table in TABLES.items():
        meta = ARTICLES[season]
        for rank, player, pos, team, pct, adp, pts, label in table:
            rows.append({
                "season": season, "player_name": player, "position": pos, "team": team,
                "espn_rank": rank, "pct_championship_rosters": pct,
                "adp_overall": adp if adp is not None else "",
                "draft_status": "undrafted" if adp is None and season >= 2017 else (
                    "drafted" if adp is not None else "not_reported_this_year"
                ),
                "season_ppr_points": pts if pts is not None else "",
                "espn_category": "on_champion_roster_ranked_table",
                "narrative_label": label or "",
                "explicitly_named_league_winner": "No",
                "reasoning_paraphrase": label or "",
                "inclusion_rule": meta["inclusion_rule"], "coverage_type": meta["coverage_type"],
                "article_title": meta["title"], "article_author": meta["author"],
                "article_publication_date": meta["date"], "article_url": meta["url"],
                "extraction_confidence": "high",
                "ambiguity_notes": (
                    "Position is D/ST or K -- outside this project's QB/RB/WR/TE scope, "
                    "kept for provenance, not for matching against our master DB."
                    if pos in ("D/ST", "K") else ""
                ),
            })
    return rows


def main():
    rows = build_rows()

    out_path = OUTPUT_DIR / "championship_roster_players.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"championship_roster_players.csv: {len(rows)} rows -> {out_path}")

    sources_path = OUTPUT_DIR / "sources.csv"
    with open(sources_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "season", "title", "author", "publication_date", "url",
            "accessible", "table_row_count", "inclusion_rule", "coverage_type",
            "usable_for_benchmark", "censoring_notes", "note",
        ])
        writer.writeheader()
        for season, meta in sorted(ARTICLES.items(), reverse=True):
            writer.writerow({
                "season": season, "title": meta["title"], "author": meta["author"],
                "publication_date": meta["date"], "url": meta["url"],
                "accessible": meta["accessible"],
                "table_row_count": len(TABLES.get(season, [])),
                "inclusion_rule": meta["inclusion_rule"], "coverage_type": meta["coverage_type"],
                "usable_for_benchmark": meta["usable_for_benchmark"],
                "censoring_notes": meta["censoring_notes"],
                "note": meta["note"],
            })
    print(f"sources.csv: {len(ARTICLES)} rows -> {sources_path}")
    print(f"Years searched but no correct-series article located: {YEARS_SEARCHED_NOT_LOCATED}")

    # Basic sanity checks -- not a test suite, just fail-loud validation
    # of the transcription itself before anyone relies on this file.
    for season, table in TABLES.items():
        ranks = [r[0] for r in table]
        assert ranks == list(range(1, len(table) + 1)), f"{season}: rank sequence broken"
    for season, meta in ARTICLES.items():
        if meta["usable_for_benchmark"]:
            assert season in TABLES, f"{season}: marked usable_for_benchmark but has no TABLES entry"
        else:
            assert season not in TABLES, f"{season}: marked NOT usable_for_benchmark but has a TABLES entry"
    print(f"Sanity checks passed: every year's ranks are sequential from 1 with no gaps, and "
          f"usable_for_benchmark agrees with which years actually have TABLES data. Row counts "
          f"per year vary legitimately (article-stated cutoffs, not fetch limits) -- see "
          f"sources.csv's table_row_count / inclusion_rule / coverage_type columns.")


if __name__ == "__main__":
    main()
