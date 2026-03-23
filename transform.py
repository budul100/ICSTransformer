import re
import json
from pathlib import Path
from datetime import datetime, timezone as dt_timezone
from icalendar import Calendar, Event

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


def detect_source(cal: Calendar, sources: list) -> list:
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
    """Set DTSTART and DTEND timezone based on the GEO field of the event."""
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


def transform_ics(input_path: str, rules_path: str, output_path: str):
    rules = load_rules(rules_path)
    cal_data = Path(input_path).read_bytes()
    cal = Calendar.from_ical(cal_data)

    matched_sources = detect_source(cal, rules.get("sources", []))
    source_rules = []
    geo_swapped = False
    for src in matched_sources:
        source_rules.extend(src.get("rules", []))
        if src.get("geo_swapped", False):
            geo_swapped = True
        print(f"Matched source: {src.get('name', '?')}")

    global_rules = rules.get("global_rules", [])

    new_cal = Calendar()
    for key, val in cal.items():
        new_cal.add(key, val)

    events = [c for c in cal.walk() if c.name == "VEVENT"]
    print(f"Processing {len(events)} event(s)...")

    for i, component in enumerate(cal.walk()):
        if component.name == "VEVENT":
            summary = str(component.get("SUMMARY", "?"))
            print(f"  [{i}] {summary}")
            transform_event(component, source_rules, global_rules)
            apply_geo_timezone(component, geo_swapped=geo_swapped)
            new_cal.add_component(component)

    Path(output_path).write_bytes(new_cal.to_ical())
    print(f"\nDone: {output_path}")


if __name__ == "__main__":
    import sys
    rules_path = Path(__file__).parent / "rules.json"
    transform_ics(sys.argv[1], str(rules_path), sys.argv[2])
