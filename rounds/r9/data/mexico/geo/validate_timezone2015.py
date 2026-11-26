"""Compare pinned tzdb offsets and required 2015 fold/gap behavior."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo


def load(raw, name):
    with (raw / "compiled_tzif" / name).open("rb") as handle:
        return ZoneInfo.from_file(handle, key=name)


def valid_offsets(local, zone):
    timestamp = dt.datetime.fromisoformat(local)
    offsets = set()
    for fold in (0, 1):
        aware = timestamp.replace(tzinfo=zone, fold=fold)
        if aware.astimezone(dt.timezone.utc).astimezone(zone).replace(tzinfo=None) == timestamp:
            offsets.add(aware.utcoffset().total_seconds() / 3600)
    return sorted(offsets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    if not shutil.which("zic"):
        raise RuntimeError("Existing zic compiler is required; no installation is attempted")
    if (args.raw_dir / "version").read_text().strip() != "2026c":
        raise RuntimeError("Wrong pinned tzdb version")
    subprocess.run([shutil.which("zic"), "-d", str(args.raw_dir / "compiled_tzif"), str(args.raw_dir / "northamerica")], check=True, capture_output=True)
    names = ["America/Mexico_City", "America/Tijuana", "America/Mazatlan", "America/Merida", "America/Monterrey", "America/Cancun", "America/Hermosillo", "America/Bahia_Banderas"]
    results = []
    for name in names:
        frozen, runtime = load(args.raw_dir, name), ZoneInfo(name)
        differences = 0
        for day in range(365):
            for hour in (0, 12):
                stamp = dt.datetime(2015, 1, 1, hour) + dt.timedelta(days=day)
                differences += stamp.replace(tzinfo=frozen).utcoffset() != stamp.replace(tzinfo=runtime).utcoffset()
        results.append({"zone": name, "compiled_tzdb": "2026c", "daily_noon_midnight_comparisons": 730,
                        "system_offset_disagreements": differences,
                        "offset_january_hours": dt.datetime(2015, 1, 15, 12, tzinfo=frozen).utcoffset().total_seconds() / 3600,
                        "offset_july_hours": dt.datetime(2015, 7, 15, 12, tzinfo=frozen).utcoffset().total_seconds() / 3600})
    cases = [("America/Cancun", "2015-02-01T02:30:00", 0), ("America/Mexico_City", "2015-04-05T02:30:00", 0),
             ("America/Mexico_City", "2015-10-25T01:30:00", 2), ("America/Tijuana", "2015-03-08T02:30:00", 0),
             ("America/Tijuana", "2015-11-01T01:30:00", 2)]
    tests = []
    for name, timestamp, expected in cases:
        actual = valid_offsets(timestamp, load(args.raw_dir, name))
        tests.append({"zone": name, "local": timestamp, "valid_utc_offsets_hours": actual,
                      "expected_valid_instant_count": expected, "pass": len(actual) == expected})
    output = {"zone_checks": results, "transition_checks": tests,
              "scope": "Offset/transition checks only; does not prove locality geography or source birth-clock precision."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    if any(row["system_offset_disagreements"] for row in results) or not all(row["pass"] for row in tests):
        raise RuntimeError("Timezone verification differs; review runtime pin before sampling")
    print("5840 offset comparisons and 5 transition cases passed")


if __name__ == "__main__":
    main()
