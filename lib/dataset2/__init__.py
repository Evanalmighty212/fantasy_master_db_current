"""
lib/dataset2/

Production modules implementing Dataset 2 (League Winner Traits)
hypothesis families -- see research/dataset2/DATASET2_TRAIT_ROADMAP.md
(the approved roadmap and per-family build decisions) and
docs/LEAGUE_WINNER_TRAITS_SPEC.md (methodology: leakage rule,
missingness policy, era/position controls, testing framework). Mirrors
lib/stars_by_value/'s placement convention: business logic lives here,
fetch/cache infrastructure (nflverse_source.py) stays in scripts/.
"""
