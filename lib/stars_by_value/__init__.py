"""
lib/stars_by_value/

Production modules that implement Stars-by-Value methodology (see
research/dataset3/STARS_BY_VALUE_METHODOLOGY.md, the settled record,
and research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md, the
build plan). Reserved for modules that apply SBV business logic --
production scoring, expected-production fitting, acquisition-cost
classification, labeling. Fetch/cache infrastructure with no SBV
methodology of its own (nflverse_source.py, mfl_client.py) lives in
scripts/ instead -- see the implementation plan's section 3/4 for that
placement decision.
"""
