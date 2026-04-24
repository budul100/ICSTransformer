import re
import json
from pathlib import Path
from datetime import date, datetime, timedelta, timezone as dt_timezone
from icalendar import Calendar, Event, Timezone, TimezoneStandard, TimezoneDaylight, vRecur

try:
    from timezonefinder import TimezoneFinder
    import pytz
    _tf = TimezoneFinder()
    TIMEZONE_SUPPORT = True
except ImportError:
    TIMEZONE_SUPPORT = False
    print("Warning: timezonefinder or pytz not installed. Timezone conversion disabled.")


def load_rules(rules_path: str) -> dict:
    with open(rules_path, encoding="utf-8-sig") as f:
        return json.load(f)


def detect_calendar_sources(cal: Calendar, sources: list) -> list:
    """Return sources whose calendar-level match (e.g. PRODID) applies."""
    matched = []
    for source in sources:
        m = source.get("match", {})
        field_val = str(cal.get(m.get("field", "PRODID"), ""))
        try:
            if re.search(m.get("pattern", ".*"), field_val):
                matched.append(source)
        except re.error as e:
            print(f"Warning: Invalid regex in source '{source.get('name', '?')}': {e}")
    return matched


def event_matches_source(event: Event, source: dict) -> bool:
    """Check optional event-level match. If no event_match defined, always True."""
    em = source.get("event_match")
    if not em:
        return True
    field_val = str(event.get(em.get("field", "SUMMARY"), ""))
    try:
        return bool(re.search(em.get("pattern", ".*"), field_val))
    except re.error as e:
        print(f"Warning: Invalid regex in event_match for '{source.get('name', '?')}': {e}")
        return False


def apply_rules(value: str, rules: list) -> str:
    for rule in rules:
        value = re.sub(rule["pattern"], rule["replace"], value)
    return value


def transform_event(event: Event, rules: list, global_rules: list) -> Event:
    for rule in global_rules + rules:
        field = rule["field"]
        if rule.get("delete", False):
            if field in event:
                del event[field]
        elif "set" in rule:
            if field in event:
                del event[field]
            event.add(field, rule["set"])
        elif "copy_from" in rule:
            source_field = rule["copy_from"]
            if source_field not in event:
                continue
            source_val = str(event[source_field])
            transformed = apply_rules(source_val, [rule])
            if field in event:
                del event[field]
            event.add(field, transformed)
        else:
            if field not in event:
                continue
            original = str(event[field])
            transformed = apply_rules(original, [rule])
            if field in event:
                del event[field]
            event.add(field, transformed)
    return event


def apply_geo_timezone(event: Event, geo_swapped: bool = False):
    """Convert DTSTART/DTEND from UTC to local timezone based on GEO field."""
    if not TIMEZONE_SUPPORT:
        return
    if "GEO" not in event or "DTSTART" not in event:
        return

    geo = event.get("GEO")
    if geo_swapped:
        lng, lat = float(geo.latitude), float(geo.longitude)
    else:
        lat, lng = float(geo.latitude), float(geo.longitude)

    tz_name = _tf.timezone_at(lat=lat, lng=lng)
    if not tz_name:
        return

    tz = pytz.timezone(tz_name)

    for field in ("DTSTART", "DTEND"):
        if field not in event:
            continue
        dt = event.decoded(field)
        if not isinstance(dt, datetime):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        dt_local = dt.astimezone(tz)
        del event[field]
        event.add(field, dt_local)


def resolve_geo_timezone(event: Event, geo_swapped: bool = False):
    """Return a pytz timezone based on the GEO field, or UTC as fallback."""
    if TIMEZONE_SUPPORT and "GEO" in event:
        geo = event.get("GEO")
        if geo_swapped:
            lng, lat = float(geo.latitude), float(geo.longitude)
        else:
            lat, lng = float(geo.latitude), float(geo.longitude)
        tz_name = _tf.timezone_at(lat=lat, lng=lng)
        if tz_name:
            return pytz.timezone(tz_name)
    return pytz.utc if TIMEZONE_SUPPORT else None


def expand_nightly(event: Event, expand_rule: dict, geo_swapped: bool = False) -> list:
    """
    Expand a VALUE=DATE all-day event into individual nightly events
    (mode: 'expand', the default) or a single recurring event (mode: 'series').

    Each night runs from time_start on day N to time_end on day N+1.
    DTEND (exclusive) minus 2 days = last night start date.
    Returns a list of Event objects.
    If the event is not a DATE-only event, returns the original unchanged.
    """
    dtstart = event.decoded("DTSTART")
    dtend   = event.decoded("DTEND")

    if not isinstance(dtstart, date) or isinstance(dtstart, datetime):
        return [event]

    start_h, start_m = map(int, expand_rule["time_start"].split(":"))
    end_h,   end_m   = map(int, expand_rule["time_end"].split(":"))
    mode = expand_rule.get("mode", "expand")

    tz = resolve_geo_timezone(event, geo_swapped)

    def localize(d, h, m):
        dt = datetime(d.year, d.month, d.day, h, m)
        return tz.localize(dt) if tz else dt

    # DTEND is exclusive; last night ends morning of (DTEND - 1), starts evening of (DTEND - 2)
    last_night_start = dtend - timedelta(days=2)
    night_count = (last_night_start - dtstart).days + 1

    if night_count < 1:
        return [event]

    if mode == "series":
        new_event = Event()
        for key, val in event.items():
            if key not in ("DTSTART", "DTEND"):
                new_event.add(key, val)

        first_start = localize(dtstart, start_h, start_m)
        first_end   = localize(dtstart + timedelta(days=1), end_h, end_m)
        new_event.add("DTSTART", first_start)
        new_event.add("DTEND",   first_end)
        new_event.add("RRULE",   {"FREQ": ["DAILY"], "COUNT": [night_count]})
        return [new_event]

    else:  # mode == "expand"
        expanded = []
        current = dtstart
        while current <= last_night_start:
            new_event = Event()
            for key, val in event.items():
                if key not in ("DTSTART", "DTEND"):
                    new_event.add(key, val)
            new_event.add("DTSTART", localize(current,                    start_h, start_m))
            new_event.add("DTEND",   localize(current + timedelta(days=1), end_h,   end_m))
            expanded.append(new_event)
            current += timedelta(days=1)
        return expanded


def build_vtimezone(tz_name: str) -> Timezone:
    """Build a VTIMEZONE component for the given IANA timezone name."""
    tz = pytz.timezone(tz_name)
    tzc = Timezone()
    tzc.add("TZID", tz_name)

    std = TimezoneStandard()
    std.add("TZNAME",       tz.localize(datetime(2026, 1, 1)).strftime("%Z"))
    std.add("DTSTART",      datetime(1970, 1, 1))
    std.add("TZOFFSETFROM", tz.localize(datetime(2026, 6, 1)).utcoffset())
    std.add("TZOFFSETTO",   tz.localize(datetime(2026, 1, 1)).utcoffset())
    tzc.add_component(std)

    dst = TimezoneDaylight()
    dst.add("TZNAME",       tz.localize(datetime(2026, 6, 1)).strftime("%Z"))
    dst.add("DTSTART",      datetime(1970, 6, 1))
    dst.add("TZOFFSETFROM", tz.localize(datetime(2026, 1, 1)).utcoffset())
    dst.add("TZOFFSETTO",   tz.localize(datetime(2026, 6, 1)).utcoffset())
    tzc.add_component(dst)

    return tzc


def collect_tz(event: Event, used_timezones: set):
    """Add timezone names from DTSTART/DTEND of an event to the set."""
    for field in ("DTSTART", "DTEND"):
        if field in event:
            dt = event.decoded(field)
            if isinstance(dt, datetime) and dt.tzinfo is not None:
                tz_name = dt.tzinfo.zone if hasattr(dt.tzinfo, "zone") else str(dt.tzinfo)
                used_timezones.add(tz_name)


def transform_ics(input_path: str, rules_path: str, output_path: str):
    rules    = load_rules(rules_path)
    cal_data = Path(input_path).read_bytes()
    cal      = Calendar.from_ical(cal_data)

    cal_sources = detect_calendar_sources(cal, rules.get("sources", []))
    for src in cal_sources:
        print(f"Matched calendar source: {src.get('name', '?')}")

    global_rules = rules.get("global_rules", [])

    new_cal = Calendar()
    for key, val in cal.items():
        new_cal.add(key, val)

    events = [c for c in cal.walk() if c.name == "VEVENT"]
    print(f"Processing {len(events)} event(s)...")

    used_timezones = set()

    for i, component in enumerate(cal.walk()):
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", "?"))
        print(f"  [{i}] {summary}")

        event_sources = [s for s in cal_sources if event_matches_source(component, s)]
        for src in event_sources:
            print(f"    -> Matched event source: {src.get('name', '?')}")

        source_rules = []
        geo_swapped  = False
        expand_rule  = None
        for src in event_sources:
            source_rules.extend(src.get("rules", []))
            if src.get("geo_swapped", False):
                geo_swapped = True
            if "expand_nightly" in src and expand_rule is None:
                expand_rule = src["expand_nightly"]

        transform_event(component, source_rules, global_rules)

        dtstart      = component.decoded("DTSTART")
        is_date_only = isinstance(dtstart, date) and not isinstance(dtstart, datetime)

        if expand_rule and is_date_only:
            result = expand_nightly(component, expand_rule, geo_swapped=geo_swapped)
            mode   = expand_rule.get("mode", "expand")
            print(f"    -> Mode '{mode}': {len(result)} event(s) generated")
            for ev in result:
                collect_tz(ev, used_timezones)
                new_cal.add_component(ev)
        else:
            apply_geo_timezone(component, geo_swapped=geo_swapped)
            collect_tz(component, used_timezones)
            new_cal.add_component(component)

    for tz_name in used_timezones:
        try:
            new_cal.add_component(build_vtimezone(tz_name))
        except Exception as e:
            print(f"Warning: Could not build VTIMEZONE for {tz_name}: {e}")

    Path(output_path).write_bytes(new_cal.to_ical())
    print(f"\nDone: {output_path}")


if __name__ == "__main__":
    import sys
    rules_path = Path(__file__).parent / "rules.json"
    transform_ics(sys.argv[1], str(rules_path), sys.argv[2])
