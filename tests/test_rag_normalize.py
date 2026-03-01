from rag.indexing.normalize import normalize_records


def test_normalize_records_maps_bulletin_to_cab_compatible_shape() -> None:
    cab_records = [
        {
            "course_code": "CSCI 0111",
            "title": "Computing Foundations",
            "instructor": [{"name": "Ada Lovelace", "email": "ada@brown.edu"}],
            "meetings": ["MWF 10:00"],
            "prerequisites": None,
            "department": "CSCI",
            "description": "Intro course.",
            "source": "CAB",
            "course_url": "https://cab.example/course/1",
        }
    ]
    bulletin_records = [
        {
            "course_code": "BIOL 3001",
            "title": "Clerkship in Medicine",
            "description": "Twelve weeks.",
            "source": "bulletin",
        }
    ]

    documents = normalize_records(cab_records=cab_records, bulletin_records=bulletin_records)

    assert len(documents) == 2

    cab_doc = documents[0]
    assert cab_doc.source == "cab"
    assert cab_doc.source_label == "CAB"
    assert cab_doc.department == "CSCI"
    assert cab_doc.instructor_names == ["Ada Lovelace"]
    assert cab_doc.course_url == "https://cab.example/course/1"

    bulletin_doc = documents[1]
    assert bulletin_doc.source == "bulletin"
    assert bulletin_doc.source_label == "bulletin"
    assert bulletin_doc.department is None
    assert bulletin_doc.prerequisites is None
    assert bulletin_doc.meetings == []
    assert bulletin_doc.instructor_names == []
    assert bulletin_doc.course_url is None


def test_doc_id_is_deterministic() -> None:
    cab_records = [
        {
            "course_code": "MATH 0100",
            "title": "Single Variable Calculus",
            "instructor": [],
            "meetings": [],
            "prerequisites": None,
            "department": "MATH",
            "description": "Limits and derivatives",
            "source": "CAB",
            "course_url": "https://example",
        }
    ]

    first = normalize_records(cab_records=cab_records, bulletin_records=[])[0]
    second = normalize_records(cab_records=cab_records, bulletin_records=[])[0]

    assert first.doc_id == second.doc_id
