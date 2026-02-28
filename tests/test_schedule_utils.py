from datetime import time

from chatbot_agent.schedule_utils import (
    ParsedMeeting,
    matches_schedule_filter,
    normalize_day_filter,
    parse_meeting_time,
    parse_user_time,
)


class TestParseMeetingTime:
    def test_simple_friday(self) -> None:
        result = parse_meeting_time("F 3pm-5:30pm")
        assert result is not None
        assert result.days == ["F"]
        assert result.start_time == time(15, 0)
        assert result.end_time == time(17, 30)

    def test_mwf(self) -> None:
        result = parse_meeting_time("MWF 9am-9:50am")
        assert result is not None
        assert result.days == ["M", "W", "F"]
        assert result.start_time == time(9, 0)
        assert result.end_time == time(9, 50)

    def test_tth(self) -> None:
        result = parse_meeting_time("TTh 1pm-2:20pm")
        assert result is not None
        assert result.days == ["T", "Th"]
        assert result.start_time == time(13, 0)
        assert result.end_time == time(14, 20)

    def test_single_monday(self) -> None:
        result = parse_meeting_time("M 3pm-5:30pm")
        assert result is not None
        assert result.days == ["M"]
        assert result.start_time == time(15, 0)

    def test_mtwhf(self) -> None:
        result = parse_meeting_time("MTWThF 10am-10:50am")
        assert result is not None
        assert result.days == ["M", "T", "W", "Th", "F"]
        assert result.start_time == time(10, 0)

    def test_tba_returns_none(self) -> None:
        assert parse_meeting_time("TBA") is None

    def test_online_returns_none(self) -> None:
        assert parse_meeting_time("Course offered online") is None

    def test_date_range_returns_none(self) -> None:
        assert parse_meeting_time("(1/21 to 2/4)") is None

    def test_empty_returns_none(self) -> None:
        assert parse_meeting_time("") is None

    def test_am_pm_inference(self) -> None:
        result = parse_meeting_time("TTh 10:30am-11:50am")
        assert result is not None
        assert result.start_time == time(10, 30)
        assert result.end_time == time(11, 50)

    def test_location_suffix(self) -> None:
        result = parse_meeting_time("F 4pm-6:30pm Location TBD")
        assert result is not None
        assert result.days == ["F"]
        assert result.start_time == time(16, 0)
        assert result.end_time == time(18, 30)


class TestParseUserTime:
    def test_3pm(self) -> None:
        assert parse_user_time("3 PM") == time(15, 0)

    def test_3_colon_00_pm(self) -> None:
        assert parse_user_time("3:00 PM") == time(15, 0)

    def test_15_colon_00(self) -> None:
        assert parse_user_time("15:00") == time(15, 0)

    def test_3pm_no_space(self) -> None:
        assert parse_user_time("3pm") == time(15, 0)

    def test_9am(self) -> None:
        assert parse_user_time("9am") == time(9, 0)

    def test_12pm(self) -> None:
        assert parse_user_time("12pm") == time(12, 0)

    def test_12am(self) -> None:
        assert parse_user_time("12am") == time(0, 0)

    def test_empty(self) -> None:
        assert parse_user_time("") is None


class TestNormalizeDayFilter:
    def test_friday(self) -> None:
        assert normalize_day_filter("F") == ["F"]

    def test_friday_full(self) -> None:
        assert normalize_day_filter("Friday") == ["F"]

    def test_mwf(self) -> None:
        assert normalize_day_filter("MWF") == ["M", "W", "F"]

    def test_tth(self) -> None:
        assert normalize_day_filter("TTh") == ["T", "Th"]

    def test_case_insensitive(self) -> None:
        assert normalize_day_filter("friday") == ["F"]


class TestMatchesScheduleFilter:
    def test_friday_after_3pm(self) -> None:
        meetings = ["F 3pm-5:30pm"]
        assert matches_schedule_filter(meetings, day="F", after_time="3 PM") is True

    def test_friday_after_3pm_earlier_course(self) -> None:
        meetings = ["F 10am-12:30pm"]
        assert matches_schedule_filter(meetings, day="F", after_time="3 PM") is False

    def test_wrong_day(self) -> None:
        meetings = ["M 3pm-5:30pm"]
        assert matches_schedule_filter(meetings, day="F") is False

    def test_day_only(self) -> None:
        meetings = ["MWF 9am-9:50am"]
        assert matches_schedule_filter(meetings, day="W") is True

    def test_before_time(self) -> None:
        meetings = ["TTh 9am-10:20am"]
        assert matches_schedule_filter(meetings, before_time="10 AM") is True

    def test_before_time_fails(self) -> None:
        meetings = ["TTh 2:30pm-3:50pm"]
        assert matches_schedule_filter(meetings, before_time="10 AM") is False

    def test_no_filter(self) -> None:
        meetings = ["TTh 1pm-2:20pm"]
        assert matches_schedule_filter(meetings) is True

    def test_tba_no_match(self) -> None:
        meetings = ["TBA"]
        assert matches_schedule_filter(meetings, day="F") is False

    def test_multiple_meetings_one_matches(self) -> None:
        meetings = ["MWF 9am-9:50am", "F 3pm-5:30pm"]
        assert matches_schedule_filter(meetings, day="F", after_time="3 PM") is True
