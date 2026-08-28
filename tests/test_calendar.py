"""Tests for the iCal parsing and display grouping in app.calendar."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.calendar import (
    CalendarEvent,
    _day_label,
    _ensure_future_events,
    _parse_events,
    _to_utc_datetime,
    prepare_display,
)

HELSINKI = ZoneInfo("Europe/Helsinki")
TODAY = date(2026, 8, 27)  # a Thursday
FI_WEEKDAYS = [
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
]


def _ics(*vevents: str) -> bytes:
    body = "\n".join(vevents)
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        f"{body}\r\nEND:VCALENDAR\r\n"
    ).encode()


def _vevent(uid: str, extra: str, summary: str = "Tapahtuma") -> str:
    return f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\n{extra}\r\nEND:VEVENT"


def test_to_utc_datetime_keeps_an_aware_datetime() -> None:
    dt = datetime(2026, 8, 27, 9, 0, tzinfo=HELSINKI)
    assert _to_utc_datetime(dt) is dt


def test_to_utc_datetime_tags_a_naive_datetime_as_utc() -> None:
    """It tags rather than converts - a naive 09:00 stays 09:00."""
    result = _to_utc_datetime(datetime(2026, 8, 27, 9, 0))  # noqa: DTZ001
    assert result == datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def test_to_utc_datetime_promotes_a_date_to_utc_midnight() -> None:
    assert _to_utc_datetime(date(2026, 8, 27)) == datetime(2026, 8, 27, tzinfo=UTC)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x/basic.ics", "https://x/basic.ics?futureevents=true"),
        ("https://x/basic.ics?foo=1", "https://x/basic.ics?foo=1&futureevents=true"),
        (
            "https://x/basic.ics?futureevents=true",
            "https://x/basic.ics?futureevents=true",
        ),
        (
            "https://x/basic.ics?futureevents=false",
            "https://x/basic.ics?futureevents=false",
        ),
    ],
)
def test_ensure_future_events(url: str, expected: str) -> None:
    assert _ensure_future_events(url) == expected


def test_day_label_names_today_and_tomorrow() -> None:
    assert _day_label(TODAY, TODAY, FI_WEEKDAYS) == "Tänään"
    assert _day_label(TODAY + timedelta(days=1), TODAY, FI_WEEKDAYS) == "Huomenna"


def test_day_label_falls_back_to_a_finnish_weekday() -> None:
    assert _day_label(TODAY + timedelta(days=2), TODAY, FI_WEEKDAYS) == "Lauantai 29.8."


def test_parses_a_timed_event() -> None:
    raw = _ics(
        _vevent("1", "DTSTART:20260827T090000Z\r\nDTEND:20260827T100000Z", "Palaveri")
    )
    events = _parse_events(raw, TODAY)
    assert len(events) == 1
    assert events[0].title == "Palaveri"
    assert events[0].start == datetime(2026, 8, 27, 9, 0, tzinfo=UTC)
    assert events[0].end == datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
    assert not events[0].all_day


def test_parses_an_all_day_event() -> None:
    raw = _ics(_vevent("1", "DTSTART;VALUE=DATE:20260828", "Vapaapäivä"))
    events = _parse_events(raw, TODAY)
    assert len(events) == 1
    assert events[0].all_day
    assert events[0].start == datetime(2026, 8, 28, tzinfo=UTC)


def test_event_without_dtend_ends_when_it_starts() -> None:
    raw = _ics(_vevent("1", "DTSTART:20260827T090000Z"))
    events = _parse_events(raw, TODAY)
    assert events[0].start == events[0].end


def test_event_without_dtstart_is_skipped() -> None:
    raw = _ics(_vevent("1", "DTEND:20260827T100000Z"))
    assert _parse_events(raw, TODAY) == []


def test_drops_events_before_today() -> None:
    raw = _ics(
        _vevent("1", "DTSTART:20260825T090000Z\r\nDTEND:20260825T100000Z", "Mennyt")
    )
    assert _parse_events(raw, TODAY) == []


def test_drops_events_past_the_seven_day_horizon() -> None:
    raw = _ics(
        _vevent("1", "DTSTART:20260910T090000Z\r\nDTEND:20260910T100000Z", "Kaukana")
    )
    assert _parse_events(raw, TODAY) == []


def test_keeps_an_event_still_running_from_before_today() -> None:
    """A multi-day event that started earlier is still relevant."""
    raw = _ics(
        _vevent("1", "DTSTART:20260825T090000Z\r\nDTEND:20260830T100000Z", "Loma")
    )
    events = _parse_events(raw, TODAY)
    assert [e.title for e in events] == ["Loma"]


def test_sorts_events_by_start() -> None:
    raw = _ics(
        _vevent("1", "DTSTART:20260829T090000Z\r\nDTEND:20260829T100000Z", "Myöhempi"),
        _vevent("2", "DTSTART:20260827T090000Z\r\nDTEND:20260827T100000Z", "Aiempi"),
    )
    assert [e.title for e in _parse_events(raw, TODAY)] == ["Aiempi", "Myöhempi"]


def test_expands_a_weekly_recurrence_within_the_window() -> None:
    raw = _ics(
        _vevent(
            "1",
            "DTSTART:20260820T090000Z\r\nDTEND:20260820T100000Z\r\n"
            "RRULE:FREQ=WEEKLY;COUNT=10",
            "Viikkopalaveri",
        )
    )
    events = _parse_events(raw, TODAY)
    # 7-day horizon from Thursday the 27th catches the 27th and the 3rd
    assert [e.start.date() for e in events] == [date(2026, 8, 27), date(2026, 9, 3)]


def test_recurrence_honours_exdate() -> None:
    raw = _ics(
        _vevent(
            "1",
            "DTSTART:20260820T090000Z\r\nDTEND:20260820T100000Z\r\n"
            "RRULE:FREQ=WEEKLY;COUNT=10\r\nEXDATE:20260827T090000Z",
            "Viikkopalaveri",
        )
    )
    events = _parse_events(raw, TODAY)
    assert [e.start.date() for e in events] == [date(2026, 9, 3)]


def test_unparseable_rrule_drops_the_event_rather_than_raising() -> None:
    raw = _ics(
        _vevent(
            "1",
            "DTSTART:20260820T090000Z\r\nDTEND:20260820T100000Z\r\nRRULE:FREQ=NONSENSE",
        )
    )
    assert _parse_events(raw, TODAY) == []


NOW = datetime(2026, 8, 27, 8, 0, tzinfo=HELSINKI)


def _event(
    title: str, start: datetime, *, all_day: bool = False, hours: int = 1
) -> CalendarEvent:
    return CalendarEvent(
        title=title, start=start, end=start + timedelta(hours=hours), all_day=all_day
    )


def test_prepare_display_groups_events_under_a_day_label() -> None:
    events = [
        _event("Aamu", datetime(2026, 8, 27, 9, 0, tzinfo=HELSINKI)),
        _event("Iltapäivä", datetime(2026, 8, 27, 14, 0, tzinfo=HELSINKI)),
        _event("Huomen", datetime(2026, 8, 28, 9, 0, tzinfo=HELSINKI)),
    ]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert [g.label for g in groups] == ["Tänään", "Huomenna"]
    assert [e.title for e in groups[0].events] == ["Aamu", "Iltapäivä"]
    assert [e.time_label for e in groups[0].events] == ["09:00-10:00", "14:00-15:00"]


def test_prepare_display_drops_the_end_time_when_the_event_ends_another_day() -> None:
    """A date next to the end time would not fit the column."""
    events = [_event("Reissu", datetime(2026, 8, 27, 22, 0, tzinfo=HELSINKI), hours=5)]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert groups[0].events[0].time_label == "22:00"


def test_prepare_display_drops_the_end_time_for_zero_length_events() -> None:
    """Feeds that omit DTEND parse as start == end."""
    events = [
        _event("Muistutus", datetime(2026, 8, 27, 9, 0, tzinfo=HELSINKI), hours=0)
    ]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert groups[0].events[0].time_label == "09:00"


def test_prepare_display_leaves_all_day_events_without_a_time() -> None:
    events = [_event("Juhannus", datetime(2026, 8, 27, tzinfo=UTC), all_day=True)]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert groups[0].events[0].time_label == ""


def test_prepare_display_pulls_a_running_all_day_event_to_today() -> None:
    """A holiday that started last week should read as Tänään, not a past date."""
    events = [_event("Loma", datetime(2026, 8, 24, tzinfo=UTC), all_day=True)]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert [g.label for g in groups] == ["Tänään"]


def test_prepare_display_caps_at_five_events() -> None:
    events = [
        _event(
            f"E{i}", datetime(2026, 8, 27, 9, 0, tzinfo=HELSINKI) + timedelta(hours=i)
        )
        for i in range(8)
    ]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert sum(len(g.events) for g in groups) == 5


def test_prepare_display_handles_no_events() -> None:
    assert prepare_display([], NOW, HELSINKI, FI_WEEKDAYS) == []


# FIXME: grouping only merges *consecutive* events sharing a label, so an
# out-of-order list produces two groups with the same heading. _parse_events
# always sorts, so this is unreachable in production today - but prepare_display
# accepts any list and quietly misrenders it.
def test_prepare_display_repeats_a_label_for_unsorted_input() -> None:
    events = [
        _event("A", datetime(2026, 8, 27, 9, 0, tzinfo=HELSINKI)),
        _event("B", datetime(2026, 8, 28, 9, 0, tzinfo=HELSINKI)),
        _event("C", datetime(2026, 8, 27, 15, 0, tzinfo=HELSINKI)),
    ]
    groups = prepare_display(events, NOW, HELSINKI, FI_WEEKDAYS)
    assert [g.label for g in groups] == ["Tänään", "Huomenna", "Tänään"]
