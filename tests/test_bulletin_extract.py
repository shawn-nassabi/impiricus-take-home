from etl.bulletin_extract import parse_bulletin_lines


def test_parse_bulletin_lines_split_code_title_and_multiline_description() -> None:
    lines = [
        "Introduction",
        "Courses",
        "Undergraduate Offerings",
        "BIOL 3663. IMS-3 Pulmonary.",
        "No description available.",
        "BIOL 3670. Advanced Pulmonary.",
        "Focuses on respiratory care and clinical methods.",
        "Includes simulation-based labs.",
    ]

    records = parse_bulletin_lines(lines)

    assert len(records) == 2
    assert records[0].course_code == "BIOL 3663"
    assert records[0].title == "IMS-3 Pulmonary"
    assert records[0].description == "No description available."

    assert records[1].course_code == "BIOL 3670"
    assert records[1].title == "Advanced Pulmonary"
    assert records[1].description == (
        "Focuses on respiratory care and clinical methods. Includes simulation-based labs."
    )


def test_parse_bulletin_lines_requires_courses_heading_and_stops_at_next_heading() -> None:
    lines = [
        "BIOL 1000. Ignored Before Courses.",
        "Courses",
        "BIOL 2000. Valid Course.",
        "Topic overview.",
        "Program Requirements",
        "BIOL 3000. Ignored After Section End.",
    ]

    records = parse_bulletin_lines(lines)

    assert len(records) == 1
    assert records[0].course_code == "BIOL 2000"
    assert records[0].title == "Valid Course"
    assert records[0].description == "Topic overview."


def test_parse_bulletin_lines_defaults_description_when_missing() -> None:
    lines = [
        "Courses",
        "BIOL 1234. Cell Biology.",
        "BIOL 2345. Genetics.",
    ]

    records = parse_bulletin_lines(lines)

    assert len(records) == 2
    assert records[0].description == "No description available."
    assert records[1].description == "No description available."
    assert all(record.source == "bulletin" for record in records)
