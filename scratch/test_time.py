from datetime import datetime, timezone, timedelta

def parse_iso_datetime(value: str):
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except Exception as e:
        return None

def format_datetime_for_display(value: str) -> str:
    dt = parse_iso_datetime(value)
    if not dt:
        return value
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    ist_dt = dt.astimezone(ist_offset)
    return ist_dt.strftime("%d %b %Y, %I:%M %p")

# Test case from user screenshot
# Input: 05:58 PM IST
# toUtcIso should produce: 2026-04-22T12:28:00.000Z
test_val = "2026-04-22T12:28:00.000Z"
print(f"Input: {test_val}")
print(f"Parsed: {parse_iso_datetime(test_val)}")
print(f"Formatted: {format_datetime_for_display(test_val)}")
