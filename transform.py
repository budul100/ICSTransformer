import re
import json
from pathlib import Path
from icalendar import Calendar, Event

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
            # Overwrite or create field regardless of current value
            if field in event:
                del event[field]
            event.add(field, rule["set"])
        else:
            if field not in event:
                continue
            original = str(event[field])
            transformed = apply_rules(original, [rule])
            event[field] = transformed
    return event

def transform_ics(input_path: str, rules_path: str, output_path: str):
    rules = load_rules(rules_path)
    cal_data = Path(input_path).read_bytes()
    cal = Calendar.from_ical(cal_data)

    matched_sources = detect_source(cal, rules.get("sources", []))
    source_rules = []
    for src in matched_sources:
        source_rules.extend(src.get("rules", []))

    global_rules = rules.get("global_rules", [])

    new_cal = Calendar()
    for key, val in cal.items():
        new_cal.add(key, val)

    for component in cal.walk():
        if component.name == "VEVENT":
            transform_event(component, source_rules, global_rules)
            new_cal.add_component(component)

    Path(output_path).write_bytes(new_cal.to_ical())
    print(f"Done: {output_path}")

if __name__ == "__main__":
    import sys
    from pathlib import Path
    rules_path = Path(__file__).parent / "rules.json"
    transform_ics(sys.argv[1], str(rules_path), sys.argv[2])
