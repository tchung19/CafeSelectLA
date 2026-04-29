"""
CafeSelect Eval — Ground Truth
================================
Fill in these two sections based on your personal knowledge of the cafes.

LABELING_GROUND_TRUTH: cafes you've visited + attributes you know to be true.
  → eval checks whether the DB record matches your labels.

SEARCH_GROUND_TRUTH: queries you'd actually type + cafes you'd expect to see.
  → eval checks whether the search pipeline returns those cafes.
"""

# ── Section 1: Labeling ground truth ─────────────────────────────────────────
# For each cafe you've personally visited, add the attributes you know are true.
# The eval will fetch the cafe from the DB and compare.

LABELING_GROUND_TRUTH = [
    # Example — replace with your own:
    # {
    #     "cafe_name": "Boondocks Coffee Roasters",
    #     "attributes": {
    #         "study_friendly": True,
    #         "noise_level": "quiet",
    #         "neighborhood": "Westwood",
    #         "has_specialty_coffee": True,
    #         "has_outlets": True,   # has_outlets > 0
    #     },
    # },
]


# ── Section 2: Search ground truth ───────────────────────────────────────────
# For each query, list the cafes you'd expect to see in results.
# min_hits = minimum number of expected cafes that must appear to pass.

SEARCH_GROUND_TRUTH = [
    # Example — replace with your own:
    # {
    #     "id": 1,
    #     "query": "study friendly cafe in westwood",
    #     "expected": ["Boondocks Coffee Roasters", "Stella Coffee Westwood", "Driply Coffee Space"],
    #     "min_hits": 2,
    #     "category": "study",
    # },
    # {
    #     "id": 2,
    #     "query": "matcha cafes in santa monica",
    #     "expected": ["10 Speed Coffee", "Caffe Luxxe - Santa Monica"],
    #     "min_hits": 1,
    #     "category": "matcha",
    # },
]
