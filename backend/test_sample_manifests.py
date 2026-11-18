"""The two sample delivery manifests in examples/delivery-manifests used in the final presentation."""

import re
from pathlib import Path

from manifest import read_manifest

SAMPLES = Path(__file__).resolve().parent.parent / "examples" / "delivery-manifests"
SEED = Path(__file__).resolve().parent / "schema.sql"


# The catalog the demo starts with: every product the seed file creates.
def seeded_catalog():
    pattern = r"\((\d+), '([^']+)', '[^']*', '[^']*', [\d.]+, [\d.]+, '[^']*'\)"
    return [{"product_id": int(i), "name": name, "is_listed": True} for i, name in re.findall(pattern, SEED.read_text())]


# The good sample is accepted, merges the repeated milk line, and restocks peaches and raspberries.
def test_good_sample_has_no_problems_and_restocks_peaches_and_raspberries():
    result = read_manifest((SAMPLES / "delivery-good.csv").read_bytes(), seeded_catalog())

    assert result.ok
    quantities = {line["name"]: line["quantity"] for line in result.lines}
    assert quantities["Organic Peaches, 2 lb"] == 24
    assert quantities["Organic Raspberries, 1 lb"] == 18
    assert quantities["Organic Whole Milk, 1 gallon"] == 18   # 10 + 8 from the differently spelled line


# The problems sample is refused, with each mistake tied to its own line and nothing applied.
def test_problem_sample_is_refused_with_every_mistake_listed_by_line():
    result = read_manifest((SAMPLES / "delivery-with-problems.csv").read_bytes(), seeded_catalog())

    assert not result.ok
    assert {problem["line"] for problem in result.problems} == {3, 4, 5, 6, 7, 8}
    assert any("Strawbery" in problem["message"] for problem in result.problems)
