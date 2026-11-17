"""The two sample delivery manifests in docs/sample-data used in the final presentation."""

from pathlib import Path

from manifest import read_manifest

SAMPLES = Path(__file__).resolve().parent.parent / "docs" / "sample-data"
CATALOG = [
    {"product_id": 1, "name": "Organic Apples, 3 lb bag", "is_listed": True},
    {"product_id": 3, "name": "Organic Broccoli Crown", "is_listed": True},
    {"product_id": 9, "name": "Organic Peaches, 2 lb", "is_listed": True},
    {"product_id": 36, "name": "Organic Raspberries, 1 lb", "is_listed": True},
]


# The good sample is accepted and restocks peaches and raspberries.
def test_good_sample_has_no_problems_and_covers_peaches_and_raspberries():
    result = read_manifest((SAMPLES / "delivery-good.csv").read_bytes(), CATALOG)

    assert result.ok
    assert {line["product_id"] for line in result.lines} == {1, 3, 9, 36}


# The problems sample is refused, with each mistake tied to its own line.
def test_problem_sample_is_refused_with_every_mistake_listed_by_line():
    result = read_manifest((SAMPLES / "delivery-with-problems.csv").read_bytes(), CATALOG)

    assert not result.ok
    assert sorted(problem["line"] for problem in result.problems) == [3, 4, 5, 6]
    assert any("Dragonfruit" in problem["message"] for problem in result.problems)
