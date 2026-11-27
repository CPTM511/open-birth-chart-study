"""Extract the numeric Shoushi tables from the two forms of one pinned edition."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from html import unescape
from pathlib import Path
import re
import subprocess

from rounds.r22.degrees import MANSIONS, ShoushiScale
from rounds.r27.archive_source import digest, private_job, require, write_json


HERE = Path(__file__).resolve().parent
TURN = Fraction("365.2575")
QUARTER = TURN / 4
URLS = {
    "page": "https://zh.wikisource.org/wiki/Special:PermanentLink/1959444",
    "render": "https://zh.wikisource.org/w/index.php?title=%E5%85%83%E5%8F%B2%2F%E5%8D%B7054&oldid=1959444&action=render",
}
TRADITIONAL_MANSIONS = "角亢氐房心尾箕斗牛女虛危室壁奎婁胃昴畢觜參井鬼柳星張翼軫"
DIGITS = str.maketrans("零〇○０一二三四五六七八九", "0000123456789")
PUNCTUATION = {"六十九〈〉六四〈八０〉": "六十九〈六四〉〈八０〉", "七十二四七〉〈六九〉": "七十二〈四七〉〈六九〉"}


@dataclass(frozen=True)
class SourceTables:
    equatorial_widths: dict[str, Fraction]
    ecliptic_widths: dict[str, Fraction]
    ecliptic_knots: tuple[Fraction, ...]
    corrected_equatorial_knots: tuple[Fraction, ...]
    uncorrected_equatorial_knots: tuple[Fraction, ...]
    correction_rows: tuple[int, ...]


def text(fragment):
    plain = unescape(re.sub(r"<[^>]*>", "", fragment))
    return re.sub(r"\[[0-9]+\]|\s+", "", plain)


def section(html, start, end):
    return html.split(f'id="{start}"', 1)[1].split(f'id="{end}"', 1)[0]


def whole(label):
    if label in ("", "初"):
        return 0
    digits = label.translate(DIGITS)
    if "十" not in digits:
        return int(digits)
    tens, ones = digits.split("十")
    return 10 * int(tens or 1) + int(ones or 0)


def read_widths(html, start, end):
    chunk = section(html, start, end)
    names, widths = [], []
    pattern = rf"([{TRADITIONAL_MANSIONS}])([零〇○０一二三四五六七八九十]*)(?:〈([初分空太零〇○０一二三四五六七八九十]+)〉)?"
    for fragment in re.findall(r"<p>(.*?)</p>", chunk, re.DOTALL):
        paragraph = text(fragment)
        if paragraph.startswith("右"):
            continue
        matches = list(re.finditer(pattern, paragraph))
        for match in matches:
            name, degree, fraction = match.groups()
            names.append(name)
            fraction = fraction or ""
            tai = Fraction(3, 400) if "太" in fraction else 0
            base = whole(re.sub(r"[初分空太]", "", fraction))
            widths.append(Fraction(whole(degree)) + Fraction(base, 100) + tai)
    require("".join(names) == TRADITIONAL_MANSIONS and sum(widths) == TURN,
            f"Source mansion order or turn differs in {start}")
    return dict(zip(MANSIONS, widths, strict=True))


def parse_arc(label, corrected):
    match = re.fullmatch(r"([^〈]*)〈([^〉]+)〉〈([^〉]+)〉", PUNCTUATION.get(label, label))
    require(match is not None, "Unrecognized numeric table cell")
    degrees, hundredths, ten_thousandths = match.groups()
    def integer(chunk):
        chunk = re.sub(r"（([^）]+)）〔([^〕]+)〕", r"\2" if corrected else r"\1", chunk)
        require(len(chunk) == 2, "The table cell must have two positional digits")
        return int(chunk.translate(DIGITS))
    return Fraction(whole(degrees)) + Fraction(integer(hundredths), 100) + Fraction(integer(ten_thousandths), 10000)


def lookup_knots(html):
    raw = section(html, "黃赤道率", "推黃道宿度")
    table = re.search(r"<table[^>]*>(.*?)</table>", raw, re.DOTALL).group(1)
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL):
        rows.append([text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)])
    require(len(rows) == 94 and all(len(row) == 6 for row in rows), "Wrong number of rows or columns in the lunar table")
    require(rows[1][0] == "初" and rows[1][2] == "", "The initial accumulating coordinate differs")
    xs, corrected, original = [Fraction(0)], [Fraction(0)], [Fraction(0)]
    corrections = []
    for degree, row in enumerate(rows[2:-1], 1):
        require(whole(row[0]) == degree, "Nonconsecutive source table degree")
        xs.append(Fraction(degree))
        corrected.append(parse_arc(row[2], True))
        original.append(parse_arc(row[2], False))
        if corrected[-1] != original[-1]:
            corrections.append(degree)
    require(rows[-2][1] == "三一" and whole(rows[-1][0]) == 91, "The table's printed terminal row differs")
    xs.extend((Fraction("91.31"), QUARTER))
    end = parse_arc(rows[-1][2], True)
    require(end == Fraction("91.3125"), "The recorded terminal rate differs")
    corrected.extend((end, QUARTER))
    original.extend((end, QUARTER))
    require(all(a < b for col in (xs, corrected, original) for a, b in zip(col, col[1:])),
            "An accumulated-angle column is not strictly increasing")
    return tuple(xs), tuple(corrected), tuple(original), tuple(corrections)


def load(path):
    html = path.read_text(encoding="utf-8")
    equatorial = read_widths(html, "赤道宿度", "推冬至赤道日度")
    ecliptic = read_widths(html, "黃道宿度", "推冬至加時黃道日度")
    require(ecliptic == ShoushiScale("wikisource_san").widths, "The pinned edition no longer agrees with R22 readings")
    return SourceTables(equatorial, ecliptic, *lookup_knots(html))


def seal(first, second, output):
    tables = load(first)
    require(first.resolve() != second.resolve() and tables == load(second),
            "Numeric extractions differ between the two source formats")
    write_json(output, {
        "source_revision": 1959444,
        "formats": {key: {"url": URLS[key], "local_sha256": digest(path)}
                    for key, path in zip(URLS, (first, second), strict=True)},
        "matched_numeric_extractions": True,
        "turn_old_degrees": str(TURN),
        "equatorial_widths_old_degrees": {k: str(v) for k, v in tables.equatorial_widths.items()},
        "printed_ecliptic_widths_old_degrees": {k: str(v) for k, v in tables.ecliptic_widths.items()},
        "ecliptic_quarter_knots_old_degrees": list(map(str, tables.ecliptic_knots)),
        "equatorial_quarter_knots_old_degrees": list(map(str, tables.corrected_equatorial_knots)),
        "uncorrected_equatorial_quarter_knots_old_degrees": list(map(str, tables.uncorrected_equatorial_knots)),
        "editorially_corrected_rows": list(tables.correction_rows),
        "source_punctuation_normalization": PUNCTUATION,
    })


def acquire(job, format_name):
    job = private_job(job)
    path = job / "yuanshi.html"
    with path.open("xb") as stream:
        subprocess.run(["curl", "-fsSL", "--proto", "=https", "--retry", "1", "--max-time", "35", URLS[format_name]],
                       stdout=stream, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("acquire")
    fetch.add_argument("--job", type=Path, required=True)
    fetch.add_argument("--format", choices=URLS, required=True)
    extract = commands.add_parser("seal")
    extract.add_argument("--source", type=Path, required=True)
    extract.add_argument("--replay-source", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "acquire":
        acquire(args.job, args.format)
    else:
        seal(args.source, args.replay_source, args.output)
