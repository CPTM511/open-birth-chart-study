"""Reconcile two readings of the frozen Lyon scans and score the paired clocks."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re

from rounds.r27.analyze import load_reference
from rounds.r27.study import age_years, chart_key
from rounds.r29.clock_pairs import score as score_pairs

from .archive_source import HERE, digest, image_list, private_job, read_json, require, selected_positions


OFFSET_SECONDS = 561
LATITUDE = 45.7580
LONGITUDE = 4.8351
COHORT = "lyon1901"
NON_ACTS = {"INDEX", "CLOSE", "BLANK"}
OTHER_ACTS = {"ACK", "COURT"}
EXCLUSIONS = {"U_MIDNIGHT", "U_CLOCK", "U_TEXT", "U_DATE", "U_PLACE", "U_SEX", "U_OFFSET",
              "OUTSIDE_CITY", "OUTSIDE_YEAR"}
PRECISIONS = {"h", "half", "quarter", "minute"}


def frozen_sample(first, second):
    require(first != second, "Use separate source acquisition directories")
    source = read_json(HERE / "source_receipt.json")
    require(source["registration_sha256"] == digest(HERE / "REGISTRATION.zh.md")
            and source["volume_index_sha256"] == digest(HERE / "volumes.json"), "Registration bytes differ")
    pages = {}
    volume_frame_sizes = []
    for cote, volume in source["volumes"].items():
        number = int(cote.split("/")[1])
        prefix = volume["manifest"].removesuffix("/manifest.json")
        expected = volume["source_order_sha256"]
        for directory in (first, second):
            images = image_list(read_json(directory / "metadata" / f"{number}.json"), prefix)
            serial = json.dumps(images, ensure_ascii=False, separators=(",", ":")).encode()
            require(sha256(serial).hexdigest() == expected, "An acquired catalogue order differs from the freeze")
        frame_size = len(images) - 4
        positions = selected_positions(number, len(images))
        require(positions == [sample["position"] for sample in volume["selected"]]
                and frame_size == volume["sample_frame_count"], "A selected volume or scan size differs")
        volume_frame_sizes.append(frame_size)
        for sample in volume["selected"]:
            filename = sample["local_name"]
            require(filename == f"{number}-{sample['position']:03}.jpg", "A selected image label differs")
            for directory in (first, second):
                require(digest(directory / "scans" / filename) == sample["sha256"],
                        "An acquired image differs from the freeze")
            pages[Path(filename).stem] = frame_size
    require(len(pages) == source["scans_selected"] == 39 and len(volume_frame_sizes) == 13
            and sum(volume_frame_sizes) == source["eligible_scan_positions"], "Registered sample coverage differs")
    return pages


def transcription(path, pages, *, reverse=False):
    rows = {}
    order = []
    for line in path.read_text(encoding="ascii").splitlines():
        scan, content = line.split(maxsplit=1)
        order.append(scan)
        halves = [section.split() for section in content.split("|")]
        require(len(halves) == 2 and all(halves), "Every scan needs both half-page readings")
        if reverse:
            halves = [section[::-1] for section in halves[::-1]]
        for side, tokens in zip("LR", halves, strict=True):
            for slot, token in enumerate(tokens, 1):
                rows[scan, side, slot] = parse_token(token, allow_unread_label=not reverse)
    require(order == sorted(pages, reverse=reverse), "Transcription must cover all images in the specified order")
    return rows


def parse_token(token, *, allow_unread_label=False):
    fields = token.split("/")
    if len(fields) == 1:
        require(token in NON_ACTS, "Unknown page entry")
        return None, token
    label, *values = fields
    require(re.fullmatch(r"R?[1-9][0-9]*(?:bis)?", label)
            or (allow_unread_label and label == "?"), "Missing or unsupported act label")
    if len(values) == 1:
        require(values[0] in OTHER_ACTS | EXCLUSIONS, "Unknown reason for exclusion")
        return label, values[0]

    require(len(values) == 6, "A birth needs registration date, actual birth date, clock, sex, precision and locality")
    registered, birth, time, sex, precision, place = values
    require(all(re.fullmatch(r"[0-9]{4}", field) for field in (registered, birth, time))
            and sex in {"M", "F"} and precision in PRECISIONS and place in {"d", "c", "a"},
            "Invalid reading fields")
    declared = datetime.strptime(f"1901{registered}", "%Y%m%d").date()
    civil = datetime.strptime(f"1901{birth}{time}", "%Y%m%d%H%M")
    require(civil.date() <= declared, "Birth date follows its declaration")
    expected_minute = {"h": {0}, "half": {30}, "quarter": {15, 45}}
    require(precision == "minute" or civil.minute in expected_minute[precision], "Clock disagrees with written precision")
    return label, (declared, civil, sex, precision, place)


def birth_row(scan, label, civil, sex, precision, place):
    utc = (civil - timedelta(seconds=OFFSET_SECONDS)).replace(tzinfo=timezone.utc)
    row = {
        "study_id": sha256(f"OBS-R37|{scan}|{label}".encode()).hexdigest(),
        "source": COHORT,
        "birth_local": civil.isoformat(),
        "birth_utc": utc.isoformat().replace("+00:00", "Z"),
        "source_offset_seconds": OFFSET_SECONDS,
        "utc_offset_seconds": OFFSET_SECONDS,
        "timezone_offset_minutes": OFFSET_SECONDS / 60,
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "sex": sex,
        "calendar": "gregorian",
        "birth_country": "FR",
        "geo_precision": "municipality_reference",
        "scan_unit": scan,
        "recorded_clock_precision": precision,
        "place_basis": place,
    }
    row["calendar_years"] = age_years(row["birth_local"])
    row["chart_input_key"] = chart_key(row)
    return row


def resolve(first, second):
    pages = frozen_sample(first, second)
    inputs = ("pass_a.tsv", "pass_b.tsv", "adjudications.json")
    primary = transcription(first / inputs[0], pages)
    review = transcription(first / inputs[1], pages, reverse=True)
    adjudications = read_json(first / inputs[2])
    require(primary.keys() == review.keys(), "Resolve the scan or act inventory before scoring")

    seen_acts = set()
    resolved_disputes = set()
    label_completed = 0
    rows = []
    counts = Counter()
    for (scan, side, position), a in primary.items():
        b = review[scan, side, position]
        locator = f"{scan}:{side}{position}"
        if a[1] != b[1] or (a[0] != "?" and a[0] != b[0]):
            ruling = adjudications[locator]
            require(ruling["basis"].strip(), "Record the evidence for each adjudicated difference")
            label, value = parse_token(ruling["final"])
            resolved_disputes.add(locator)
        else:
            label, value = b
        label_completed += a[0] == "?" and b[0] != "?"
        if label is not None:
            act = (scan.split("-")[0], label)
            require(act not in seen_acts, "An act label repeats within the same volume")
            seen_acts.add(act)
        if isinstance(value, str):
            counts[value] += 1
        else:
            _, civil, sex, precision, place = value
            rows.append(birth_row(scan, label, civil, sex, precision, place))
    require(resolved_disputes == set(adjudications), "Each adjudication must correspond to a difference")
    ordinary = len(rows) + sum(counts[reason] for reason in EXCLUSIONS)
    resolved = len(rows) + counts["OUTSIDE_CITY"] + counts["OUTSIDE_YEAR"]
    require(len(rows) >= 70 and resolved / ordinary >= .85, "Registered data feasibility condition failed")

    scan_counts = Counter(row["scan_unit"] for row in rows)
    weights = [Fraction(pages[row["scan_unit"]], 3) for row in rows]
    receipt = {
        "images_read": len(pages),
        "images_with_eligible_births": len(scan_counts),
        "images_with_no_eligible_births": len(pages) - len(scan_counts),
        "non_act_entries": {key.lower(): counts[key] for key in sorted(NON_ACTS)},
        "civil_acts_read": len(seen_acts),
        "ordinary_birth_acts": ordinary,
        "ordinary_birth_acts_classifiable": resolved,
        "ordinary_classifiable_fraction": resolved / ordinary,
        "eligible_birth_acts": len(rows),
        "excluded_civil_acts": {key.lower(): value for key, value in sorted(counts.items()) if key not in NON_ACTS},
        "repeated_act_labels_within_volume": 0,
        "both_passes_cover_same_slots": True,
        "fields_or_observed_labels_disputed": len(resolved_disputes),
        "act_labels_completed_in_second_pass": label_completed,
        "same_ai_reader": True,
        "private_transcription_sha256": {name: digest(first / name) for name in inputs},
    }
    return pages, {COHORT: (rows, weights)}, receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-recheck", type=Path, required=True)
    parser.add_argument("--r10-job", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    load_reference(args.r10_job)
    _, groups, _ = resolve(private_job(args.source), private_job(args.source_recheck))
    score_pairs(groups, private_job(args.job) / "profiles.jsonl", args.jobs)
