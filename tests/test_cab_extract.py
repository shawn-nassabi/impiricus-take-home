from etl.cab_extract import parse_course_html, parse_course_payload


COURSE_HTML = """
<html>
  <body>
    <div class="dtl-course-code">CSCI 0111</div>
    <div class="text col-8 detail-title text--huge">Computing Foundations: Data</div>
    <div class="instructor">
      <span class="instructor-name">Prof. Jane Doe</span>
      <span class="truncate">jane_doe@brown.edu</span>
    </div>
    <div class="instructor">
      <span class="instructor-name">Prof. John Smith</span>
      <span class="truncate">john_smith@brown.edu</span>
    </div>
    <table class="meet">
      <tr>
        <th>Term</th>
        <th>Days</th>
        <th>Time</th>
        <th>Professor</th>
      </tr>
      <tr>
        <td>Fall 2025</td>
        <td>MWF</td>
        <td>10:00 AM - 10:50 AM</td>
        <td>Prof. Jane Doe</td>
      </tr>
      <tr>
        <td>Fall 2025</td>
        <td>R</td>
        <td>1:00 PM - 2:20 PM</td>
        <td>Prof. John Smith</td>
      </tr>
    </table>
    <h3>Registration Restrictions</h3>
    <div>Prerequisite: MATH 0090</div>
    <h3>Description</h3>
    <div class="course-description">Introduction to computing and problem solving.</div>
    <dl>
      <dt>Department</dt><dd>Computer Science</dd>
    </dl>
  </body>
</html>
"""


def test_parse_course_html_main_fields() -> None:
    record = parse_course_html(COURSE_HTML, "https://cab.brown.edu/?crse_id=1")
    data = record.to_dict()

    assert data["course_code"] == "CSCI 0111"
    assert data["title"] == "Computing Foundations: Data"
    assert data["source"] == "CAB"
    assert data["department"] == "Computer Science"
    assert data["description"] == "Introduction to computing and problem solving."
    assert "Prerequisite: MATH 0090" in data["prerequisites"]
    assert len(data["instructor"]) == 2


def test_parse_course_html_meetings_as_strings() -> None:
    record = parse_course_html(COURSE_HTML, "https://cab.brown.edu/?crse_id=1")
    assert len(record.meetings) == 2
    assert "Fall 2025 | MWF | 10:00 AM - 10:50 AM | Prof. Jane Doe" in record.meetings
    assert "Fall 2025 | R | 1:00 PM - 2:20 PM | Prof. John Smith" in record.meetings


def test_department_fallback_from_course_code() -> None:
    html = """
    <div class="dtl-course-code">PHP 1250</div>
    <div class="text col-8 detail-title text--huge">Bioethics</div>
    """
    record = parse_course_html(html, "https://cab.brown.edu/?crse_id=2")
    assert record.department == "PHP"


def test_parse_course_payload_meeting_strings() -> None:
    payload = {
        "code": "CSCI 0111",
        "title": "Computing Foundations: Data",
        "description": "<p>Intro course.</p>",
        "registration_restrictions": "<div>Prerequisite: MATH 0090</div>",
        "subject": "CSCI",
        "instructordetail_html": (
            "<div class='instructor'>"
            "<span class='instructor-name'>Prof. Jane Doe</span>"
            "<span class='truncate'>jane_doe@brown.edu</span>"
            "</div>"
        ),
        "allInGroup": [
            {
                "no": "01",
                "meets": "MWF 10:00 AM - 10:50 AM",
                "instr": "Prof. Jane Doe",
                "srcdb": "Fall 2025",
            }
        ],
        "meeting_html": (
            "<table><tr><th>Term</th><th>Days</th><th>Time</th><th>Professor</th></tr>"
            "<tr><td>Fall 2025</td><td>R</td><td>1:00 PM - 2:20 PM</td><td>Prof. John Smith</td></tr>"
            "</table>"
        ),
    }

    record = parse_course_payload(payload, "cab://group/test").to_dict()
    assert record["course_code"] == "CSCI 0111"
    assert record["title"] == "Computing Foundations: Data"
    assert record["department"] == "CSCI"
    assert "Prerequisite: MATH 0090" in (record["prerequisites"] or "")
    assert any(
        "Fall 2025 | Section 01 | MWF 10:00 AM - 10:50 AM | Prof. Jane Doe" == meeting
        for meeting in record["meetings"]
    )
    assert any(
        "Fall 2025 | R | 1:00 PM - 2:20 PM | Prof. John Smith" == meeting
        for meeting in record["meetings"]
    )
    assert any(person["name"] == "Prof. Jane Doe" for person in record["instructor"])
