# ICS Transformer – README

A lightweight Python tool to transform `.ics` calendar files using configurable regex-based rules. Useful for cleaning up calendar exports before importing them into Outlook or other clients.

---

## Requirements

- Python 3.10+
- `icalendar` library
- `timezonefinder` library
- `pytz` library

```bash
pip install icalendar timezonefinder pytz
```

---

## File Structure

```
ics_transformer/
├── transform.py      # Main script
├── rules.json        # Transformation rules
└── transform.bat     # Launcher (lives in Downloads or anywhere convenient)
```

`transform.bat` can live anywhere – just set `SCRIPT_DIR` inside it to point to the folder containing `transform.py` and `rules.json`.

---

## Usage

**Option A – Drag & Drop**

Drag any `.ics` file onto `transform.bat`. The output file is saved next to the input file with a `_transformed` suffix.

**Option B – Command Line**

```bat
transform.bat "C:\path\to\input.ics"
```

---

## Configuration – `rules.json`

Rules are split into two levels:

- **`global_rules`** – applied to every event, regardless of source
- **`sources`** – source-specific rules, activated by two optional match levels

### Source matching – two levels

**Calendar-level match** (required): identifies the source by a calendar field, typically `PRODID`:

```json
{
  "name": "My Source",
  "match": { "field": "PRODID", "pattern": ".*mysource.*" },
  "rules": [ ... ]
}
```

**Event-level match** (optional): further filters which events within a matched calendar the source rules apply to. Useful when one calendar contains different event types (e.g. flights vs. hotel stays):

```json
{
  "name": "My Source – Flights",
  "match": { "field": "PRODID", "pattern": ".*mysource.*" },
  "event_match": { "field": "DESCRIPTION", "pattern": "Flight Information" },
  "rules": [ ... ]
}
```

If `event_match` is omitted, the source rules apply to all events in the matched calendar.

> **Note:** Use `.*keyword.*` syntax for partial matches. Plain wildcards like `*keyword*` are not valid regex.

---

### Delete a field

```json
{ "field": "ORGANIZER", "delete": true }
```

Use this to remove `ORGANIZER` and `ATTENDEE` fields, which cause Outlook to treat imports as meeting invitations instead of regular appointments.

### Transform a field value with regex

```json
{
  "field": "SUMMARY",
  "pattern": ".*Flight to: (.+) from (.+)\\n\\s*\\((.+)\\)",
  "replace": "Flight: \\2 -> \\1 (\\3)"
}
```

Capture groups are referenced as `\\1`, `\\2`, `\\3` etc. in the `replace` value.

### Set a field to a fixed value

```json
{
  "field": "CATEGORIES",
  "set": "@Journey"
}
```

Creates or overwrites the field with a fixed value, regardless of its current content. Useful for assigning Outlook categories based on the event source.

For Outlook busy status, use the Microsoft-specific field `X-MICROSOFT-CDO-BUSYSTATUS`:

```json
{
  "field": "X-MICROSOFT-CDO-BUSYSTATUS",
  "set": "OOF"
}
```

Available values:

| Value | Outlook display |
|---|---|
| `FREE` | Free |
| `BUSY` | Busy (default) |
| `TENTATIVE` | Tentative |
| `OOF` | Out of Office |

### Copy and transform a value from another field

```json
{
  "field": "DESCRIPTION",
  "copy_from": "SUMMARY",
  "pattern": ".+Stay at (.+)",
  "replace": "Hotel: \\1"
}
```

Reads the value from `copy_from`, applies the regex, and writes the result into `field`. Useful for extracting partial information from one field into another.

> **Note:** Place `copy_from` rules before any regex transforms on the source field, so they still read the original value.

---

### Expanding all-day events into nightly events – `expand_nightly`

Some sources export multi-day stays as a single `VALUE=DATE` all-day event. `expand_nightly` splits this into one event per night, each running from `time_start` to `time_end` the following morning.

Add `expand_nightly` directly to the source definition (not inside `rules`):

```json
{
  "name": "My Source – Stays",
  "match": { "field": "PRODID", "pattern": ".*mysource.*" },
  "event_match": { "field": "DESCRIPTION", "pattern": "Hotel information" },
  "expand_nightly": {
    "time_start": "22:00",
    "time_end": "08:00",
    "mode": "series"
  },
  "rules": [ ... ]
}
```

**`mode`** controls how the nightly events are generated:

| Value | Behaviour |
|---|---|
| `"expand"` | One separate event per night (default if omitted) |
| `"series"` | A single recurring event with `RRULE:FREQ=DAILY;COUNT=N` |

**Night count:** for a stay with `DTSTART=Oct 3` and `DTEND=Oct 8` (exclusive), the last night ends on the morning of Oct 7, giving 4 nights. The script derives this automatically.

Timezone for `DTSTART`/`DTEND` is resolved from the `GEO` field of the event if available (see below).

---

## Automatic Timezone Detection

If a VEVENT contains a `GEO` field, the script automatically converts `DTSTART` and `DTEND` from UTC to the local timezone of that location.

Example: a flight departing Berlin (`GEO:13.405;52.52`) with `DTSTART:20260415T093000Z` becomes `DTSTART;TZID=Europe/Berlin:20260415T113000`.

This requires `timezonefinder` and `pytz` to be installed. If either is missing, the script falls back to UTC without error.

### Non-standard GEO order

Some sources (e.g. TravelPerk) write `GEO` as `longitude;latitude` instead of the standard `latitude;longitude`. This causes incorrect timezone detection. Set `geo_swapped: true` in the source definition to fix this:

```json
{
  "name": "TravelPerk",
  "match": { "field": "PRODID", "pattern": ".*travelperk.*" },
  "geo_swapped": true,
  "rules": [ ... ]
}
```

---

## Full `rules.json` Example

```json
{
  "global_rules": [
    { "field": "ORGANIZER", "delete": true },
    { "field": "ATTENDEE",  "delete": true }
  ],
  "sources": [
    {
      "name": "TravelPerk – Flights",
      "match": { "field": "PRODID", "pattern": ".*travelperk.*" },
      "event_match": { "field": "DESCRIPTION", "pattern": "Flight Information" },
      "geo_swapped": true,
      "rules": [
        {
          "field": "SUMMARY",
          "pattern": ".*Flight to: (\\S.*\\S) from (\\S.+\\S)\\s*\\(.*",
          "replace": "Flight: \\2 -> \\1"
        },
        { "field": "CATEGORIES", "set": "@Journey" },
        { "field": "X-MICROSOFT-CDO-BUSYSTATUS", "set": "OOF" }
      ]
    },
    {
      "name": "TravelPerk – Stays",
      "match": { "field": "PRODID", "pattern": ".*travelperk.*" },
      "event_match": { "field": "DESCRIPTION", "pattern": "Hotel information" },
      "geo_swapped": true,
      "expand_nightly": {
        "time_start": "22:00",
        "time_end": "08:00",
        "mode": "series"
      },
      "rules": [
        {
          "field": "DESCRIPTION",
          "copy_from": "SUMMARY",
          "pattern": ".+Stay at (.+)",
          "replace": "Hotel: \\1"
        },
        { "field": "CATEGORIES", "set": "@Journey" },
        { "field": "X-MICROSOFT-CDO-BUSYSTATUS", "set": "OOF" }
      ]
    }
  ]
}
```

---

## `transform.bat` Setup

Open `transform.bat` in a text editor and set the path to your script directory:

```bat
set SCRIPT_DIR=C:\Users\YourName\Documents\ics_transformer
```

---

## Troubleshooting

**Nothing happens / rule doesn't match**
- Open the raw `.ics` file in a text editor and check the exact format of the field you're targeting.
- Check that `\n` in the ICS is actually a literal `\n` and not a real newline.
- Verify the `PRODID` value and adjust the source `match` pattern accordingly.

**Event-level rule not applying**
- Check the `event_match` pattern against the actual `DESCRIPTION` (or whichever field you're matching). Copy the raw value from the `.ics` file to verify.

**JSON parse error (BOM)**
- Save `rules.json` as **UTF-8** or **UTF-8 without BOM**. The script handles both via `utf-8-sig` encoding.

**Emoji in patterns not working**
- Ensure `rules.json` is saved as UTF-8. Open it in VS Code and check the encoding in the bottom-right status bar.
