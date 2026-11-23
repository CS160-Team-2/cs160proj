import pytest

from manifest import MAX_BYTES, MAX_LINES, MAX_QUANTITY, read_manifest

CATALOG = [
    {"product_id": 1, "name": "Organic Apples, 3 lb bag", "is_listed": True},
    {"product_id": 2, "name": "Organic Bananas, bunch", "is_listed": True},
    {"product_id": 3, "name": "Organic Broccoli Crown", "is_listed": True},
    {"product_id": 4, "name": "Organic Eggs, dozen", "is_listed": False},
]


# A file with the ID DM-1001 added as the last column of every non-blank row.
def manifest(*rows, header="product_name,quantity"):
    stamped = [f"{row},DM-1001" if row.strip() else row for row in rows]
    return "\n".join([f"{header},manifest_id", *stamped]).encode("utf-8")


def raw_file(*rows):
    return "\n".join(["manifest_id,product_name,quantity", *rows]).encode("utf-8")


def lines_by_id(result):
    return {line["product_id"]: line for line in result.lines}


def problem_lines(result):
    return [problem["line"] for problem in result.problems]


def test_reads_each_product_and_quantity():
    result = read_manifest(manifest(
        '"Organic Apples, 3 lb bag",24',
        "Organic Broccoli Crown,30",
    ), CATALOG)

    assert result.ok and result.problems == []
    assert [(line["product_id"], line["quantity"]) for line in result.lines] == [(1, 24), (3, 30)]
    assert result.lines[0]["name"] == "Organic Apples, 3 lb bag"
    assert result.lines[0]["line_numbers"] == [2]


def test_names_match_ignoring_capitals_and_extra_spaces():
    result = read_manifest(manifest('"  organic   APPLES,  3 lb BAG ",5'), CATALOG)
    assert result.ok
    assert lines_by_id(result)[1]["quantity"] == 5


def test_header_capitals_column_order_and_extra_columns_do_not_matter():
    result = read_manifest(manifest(
        '12,PO-1182,"Organic Bananas, bunch"',
        header="Quantity,Supplier Ref,Product_Name",
    ), CATALOG)
    assert result.ok
    assert lines_by_id(result)[2]["quantity"] == 12


def test_the_same_product_on_two_lines_is_added_together():
    result = read_manifest(manifest(
        "Organic Broccoli Crown,10",
        '"Organic Apples, 3 lb bag",4',
        "organic broccoli crown,15",
    ), CATALOG)

    assert result.ok
    broccoli = lines_by_id(result)[3]
    assert broccoli["quantity"] == 25
    assert broccoli["line_numbers"] == [2, 4]
    assert [line["product_id"] for line in result.lines] == [3, 1]


def test_blank_lines_are_skipped_but_line_numbers_still_match_the_file():
    result = read_manifest(manifest("", "Organic Broccoli Crown,3", "   ", "Nope,1"), CATALOG)
    assert lines_by_id(result)[3]["line_numbers"] == [3]
    assert problem_lines(result) == [5]


def test_unlisted_products_can_be_restocked_and_are_marked():
    result = read_manifest(manifest('"Organic Eggs, dozen",6'), CATALOG)
    assert result.ok
    assert lines_by_id(result)[4]["is_listed"] is False


def test_excel_byte_order_mark_and_windows_line_endings_are_handled():
    raw = '﻿manifest_id,product_name,quantity\r\nDM-1001,Organic Broccoli Crown,7\r\n'.encode("utf-8")
    result = read_manifest(raw, CATALOG)
    assert result.ok
    assert lines_by_id(result)[3]["quantity"] == 7


def test_the_largest_allowed_quantity_is_accepted():
    result = read_manifest(manifest(f"Organic Broccoli Crown,{MAX_QUANTITY}"), CATALOG)
    assert result.ok


def test_an_unknown_product_is_a_problem_not_a_guess():
    result = read_manifest(manifest("Organic Brocoli Crown,3"), CATALOG)

    assert not result.ok
    assert problem_lines(result) == [2]
    assert 'Organic Brocoli Crown' in result.problems[0]["message"]


def test_a_name_that_matches_two_products_is_a_problem():
    catalog = CATALOG + [{"product_id": 9, "name": "organic broccoli  crown", "is_listed": True}]
    result = read_manifest(manifest("Organic Broccoli Crown,3"), catalog)
    assert problem_lines(result) == [2]
    assert "more than one product" in result.problems[0]["message"]


def test_a_missing_product_name_is_a_problem():
    result = read_manifest(manifest(",3"), CATALOG)
    assert problem_lines(result) == [2]


@pytest.mark.parametrize("quantity", ["0", "-3", "2.5", "twelve", "", "1e3", str(MAX_QUANTITY + 1)])
def test_quantity_must_be_a_whole_number_in_range(quantity):
    result = read_manifest(manifest(f"Organic Broccoli Crown,{quantity}"), CATALOG)
    assert not result.ok
    assert problem_lines(result) == [2]


def test_repeated_lines_cannot_add_up_past_the_limit():
    half = MAX_QUANTITY // 2 + 1
    result = read_manifest(manifest(
        f"Organic Broccoli Crown,{half}", f"Organic Broccoli Crown,{half}"), CATALOG)
    assert not result.ok


def test_every_problem_is_reported_at_once():
    result = read_manifest(manifest(
        "Mystery Fruit,3",
        "Organic Broccoli Crown,lots",
        '"Organic Apples, 3 lb bag",4',
        ",2",
    ), CATALOG)
    assert problem_lines(result) == [2, 3, 5]


@pytest.mark.parametrize("header", ["name,quantity", "product_name,qty", "product_name"])
def test_the_header_must_name_both_columns(header):
    result = read_manifest(manifest("Organic Broccoli Crown,3", header=header), CATALOG)
    assert not result.ok
    assert problem_lines(result) == [1]


@pytest.mark.parametrize("raw", [b"", b"product_name,quantity\n", b"product_name,quantity\n\n  \n"])
def test_a_manifest_with_no_products_is_a_problem(raw):
    result = read_manifest(raw, CATALOG)
    assert not result.ok
    assert result.lines == []


def test_a_file_that_is_not_text_is_a_problem():
    result = read_manifest(b"\x89PNG\r\n\x1a\n\x00\x00binary", CATALOG)
    assert not result.ok


def test_too_many_lines_is_a_problem():
    rows = ["Organic Broccoli Crown,1"] * (MAX_LINES + 1)
    assert not read_manifest(manifest(*rows), CATALOG).ok


def test_the_most_lines_allowed_is_accepted():
    rows = ["Organic Broccoli Crown,1"] * MAX_LINES
    assert read_manifest(manifest(*rows), CATALOG).ok


def test_a_file_over_the_size_limit_is_a_problem():
    raw = manifest("Organic Broccoli Crown,1") + b" " * MAX_BYTES
    assert not read_manifest(raw, CATALOG).ok


def test_the_same_file_always_gives_the_same_result():
    raw = manifest('"Organic Apples, 3 lb bag",24', "Mystery Fruit,1", "Organic Broccoli Crown,3")
    first, second = read_manifest(raw, CATALOG), read_manifest(raw, CATALOG)
    assert first.lines == second.lines
    assert first.problems == second.problems


def test_the_manifest_id_is_read_from_the_file():
    result = read_manifest(raw_file("DM-1001,Organic Broccoli Crown,3",
                                    'DM-1001,"Organic Apples, 3 lb bag",4'), CATALOG)
    assert result.ok
    assert result.manifest_id == "DM-1001"


def test_capitals_and_spaces_around_the_id_do_not_make_it_a_different_id():
    result = read_manifest(raw_file("  dm-1001 ,Organic Broccoli Crown,3",
                                    'DM-1001,"Organic Bananas, bunch",1'), CATALOG)
    assert result.ok
    assert result.manifest_id == "DM-1001"


def test_a_file_without_the_id_column_is_a_problem():
    result = read_manifest(b"product_name,quantity\nOrganic Broccoli Crown,3\n", CATALOG)
    assert not result.ok
    assert problem_lines(result) == [1]
    assert "manifest_id" in result.problems[0]["message"]


def test_a_line_without_an_id_is_a_problem():
    result = read_manifest(raw_file("DM-1001,Organic Broccoli Crown,3",
                                    ',"Organic Apples, 3 lb bag",4'), CATALOG)
    assert problem_lines(result) == [3]
    assert "manifest ID is missing" in result.problems[0]["message"]


def test_two_ids_in_one_file_is_a_problem():
    result = read_manifest(raw_file("DM-1001,Organic Broccoli Crown,3",
                                    'DM-1002,"Organic Apples, 3 lb bag",4'), CATALOG)
    assert problem_lines(result) == [3]
    assert "DM-1002" in result.problems[0]["message"]
    assert "DM-1001" in result.problems[0]["message"]


@pytest.mark.parametrize("bad_id", ["DM 1001", "DM#1001", "-1001", "A" * 65])
def test_an_id_with_the_wrong_shape_is_a_problem(bad_id):
    result = read_manifest(raw_file(f"{bad_id},Organic Broccoli Crown,3"), CATALOG)
    assert not result.ok
    assert problem_lines(result) == [2]
    assert result.manifest_id is None
