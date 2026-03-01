from etl.cab_extract import parse_course_html


def test_cab_record_schema_keys() -> None:
    html = """
    <div class="dtl-course-code">ENGN 0030</div>
    <div class="text col-8 detail-title text--huge">Basic Engineering</div>
    <div class="meet"><ul><li>Fall 2025 | MWF | 9:00 - 9:50 | Prof. A</li></ul></div>
    """
    record = parse_course_html(html, "https://cab.brown.edu/?crse_id=3").to_dict()
    expected_keys = {
        "course_code",
        "title",
        "instructor",
        "meetings",
        "prerequisites",
        "department",
        "description",
        "source",
        "course_url",
    }
    assert set(record.keys()) == expected_keys
    assert record["source"] == "CAB"
    assert isinstance(record["meetings"], list)
    assert all(isinstance(item, str) for item in record["meetings"])

