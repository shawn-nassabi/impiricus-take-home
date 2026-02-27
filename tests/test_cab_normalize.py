from etl.cab_normalize import (
    build_meeting_string,
    extract_email,
    infer_department_from_course_code,
    normalize_whitespace,
    unique_preserve_order,
)


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  A   B\nC\t") == "A B C"
    assert normalize_whitespace("   ") is None


def test_extract_email() -> None:
    assert extract_email("Prof: test.user@brown.edu ") == "test.user@brown.edu"
    assert extract_email("no-email") is None


def test_unique_preserve_order() -> None:
    values = unique_preserve_order([" A ", "B", "A", " ", "B", "C"])
    assert values == ["A", "B", "C"]


def test_build_meeting_string() -> None:
    assert build_meeting_string(["Fall 2025", "MWF", "10:00-10:50", "Dr. Li"]) == (
        "Fall 2025 | MWF | 10:00-10:50 | Dr. Li"
    )
    assert build_meeting_string([" ", ""]) is None


def test_department_inference() -> None:
    assert infer_department_from_course_code("CSCI 0111") == "CSCI"
    assert infer_department_from_course_code("1111") is None

