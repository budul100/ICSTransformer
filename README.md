# ICS Transformer – README

A lightweight Python tool to transform `.ics` calendar files using configurable regex-based rules. Useful for cleaning up calendar exports before importing them into Outlook or other clients.

---

## Requirements

- Python 3.10+
- `icalendar` library

```bash
pip install icalendar
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

- **`global_rules`** – applied to every file, regardless of source
- **`sources`** – source-specific rules, activated when a field (typically `PRODID`) matches a pattern

### Delete a field

```json
{
  "field": "ORGANIZER",
  "delete": true
}
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

### Source matching

Sources are identified by matching a field (usually `PRODID`) against a regex pattern:

```json
{
  "name": "TravelPerk",
  "match": { "field": "PRODID", "pattern": ".*travelperk.*" },
  "rules": [ ... ]
}
```

> **Note:** Use `.*keyword.*` syntax for partial matches. Plain wildcards like `*keyword*` are not valid regex.

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
      "name": "TravelPerk",
      "match": { "field": "PRODID", "pattern": ".*travelperk.*" },
      "rules": [
        {
          "field": "SUMMARY",
          "pattern": ".*Flight to: (.+) from (.+)\\n\\s*\\((.+)\\)",
          "replace": "Flight: \\2 -> \\1 (\\3)"
        }
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

**JSON parse error (BOM)**
- Save `rules.json` as **UTF-8** or **UTF-8 without BOM**. The script handles both via `utf-8-sig` encoding.

**Emoji in patterns not working**
- Ensure `rules.json` is saved as UTF-8. Open it in VS Code and check the encoding in the bottom-right status bar.