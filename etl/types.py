from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CabInstructor:
    name: str
    email: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CabCourseRecord:
    course_code: str
    title: str
    instructor: list[CabInstructor]
    meetings: list[str]
    prerequisites: str | None
    department: str | None
    description: str | None
    source: str
    course_url: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["instructor"] = [person.to_dict() for person in self.instructor]
        return data


@dataclass(frozen=True)
class BulletinCourseRecord:
    course_code: str
    title: str
    description: str
    source: str = "bulletin"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
