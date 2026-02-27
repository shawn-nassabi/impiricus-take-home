from etl.bulletin_extract import parse_bulletin_lines


def test_bulletin_record_schema_keys() -> None:
    lines = [
        "Courses",
        "BIOL 3663. IMS-3 Pulmonary.",
        "No description available.",
    ]
    record = parse_bulletin_lines(lines)[0].to_dict()

    expected_keys = {
        "course_code",
        "title",
        "description",
        "source",
    }
    assert set(record.keys()) == expected_keys
    assert record["source"] == "bulletin"
