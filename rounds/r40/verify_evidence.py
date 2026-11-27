"""Verify R40's archived PDF data and public web claims."""

from argparse import ArgumentParser
from hashlib import file_digest
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from pypdf import PdfReader


HERE = Path(__file__).resolve().parent
SHARING_HEADING = "개인정보를통상적또는반복적으로제공하는경우"
FIELDS_HEADING = "개인정보파일에기록되는개인정보의항목"
FOLLOWING_HEADING = "개인정보파일에서열람을제한하거나거절할수있는"
BIRTH_FIELDS = ("신생아생년월일", "신생아출생시분", "신생아성별")
WEB_MARKERS = {
    "family-rule.html": ("제38조의3", "출생자의출생순서", "출생자가실제출생한의료기관의명칭"),
    "hira-research-catalog.html": ("맞춤형연구자료", "환자표본자료", "청구명세서기반자료", "의료기관의정보가비식별처리",
                                    "방문분석", "이용수수료"),
    "law-clause.html": ("제44조의3", "출생자의성별", "출생연월일시", "출생일부터14일이내",
                        "출생자모의주소지를관할하는", "출생지를관할하는"),
    "reporting-notice.html": ("제2024-180호", "출생정보웹포털사용자매뉴얼"),
    "start-notice.html": ("출생통보제및보호출산제시행안내", "24.7.19"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compact(text):
    return re.sub(r"[\s①②③④⑤⑥⑦⑧⑨⑩⑪⑫]+", "", text)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skipping = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skipping = tag

    def handle_endtag(self, tag):
        if tag == self.skipping:
            self.skipping = None

    def handle_data(self, data):
        if self.skipping is None:
            self.parts.append(data)


def verify_ledger(page, filename, expected):
    texts = [compact(page.extract_text(extraction_mode=mode)) for mode in ("plain", "layout")]
    for text in texts:
        require("파일명출생정보" in text or "출생정보파일명" in text, f"{filename} is missing the named privacy-file entry")
        for label, field in (("연번", "entry_serial"), ("정보주체수", "information_subject_count")):
            require(f"{label}{expected[field]}" in text, f"{filename} is missing {label}")
        retention = rf"개인정보의보유기간년?{expected['retention_years']}(?![0-9])"
        require(re.search(retention, text), f"{filename} omits the stated retention period")
        holding = text.split(FIELDS_HEADING, 1)[1].split(SHARING_HEADING, 1)[0]
        sharing = text.split(SHARING_HEADING, 1)[1].split(FOLLOWING_HEADING, 1)[0]
        require(all(field in holding for field in BIRTH_FIELDS[1:]), f"{filename} omits minute or sex")
        require((BIRTH_FIELDS[0] in holding) == expected["holding_lists_newborn_birth_date_by_name"],
                f"{filename} differs on the explicit newborn date label")
        has_share_fields = all(field in sharing for field in BIRTH_FIELDS)
        require(has_share_fields == expected["routine_sharing_scope_includes_birth_date_minute_and_sex"],
                f"{filename} differs on the listed sharing fields")
        require("대법원" in sharing and "아동권리보장원" in sharing, f"{filename} differs on printed recipients")
        require("의료기관의명칭" not in sharing, f"{filename} includes a listed delivery facility")


def verify(directory, expected, side):
    for filename, source in expected["sources"].items():
        path = directory / filename
        if filename.endswith(".pdf"):
            with path.open("rb") as stream:
                actual_hash = file_digest(stream, "sha256").hexdigest()
            require(actual_hash == source["retrieval_sha256"][side], f"PDF hash differs at {filename}")
            pdf = PdfReader(path)
            require(max(source["pdf_pages"]) <= len(pdf.pages), f"Missing pages in {filename}")
            if filename in expected["privacy_register_entries"]:
                page = pdf.pages[source["pdf_pages"][0] - 1]
                verify_ledger(page, filename, expected["privacy_register_entries"][filename])
            if filename == "reporting-manual.pdf":
                text = compact(" ".join(pdf.pages[i - 1].extract_text() for i in source["pdf_pages"]))
                require("2024년7월19일부터시행" in text and "출생연월일시" in text and "14일이내" in text,
                        "HIRA reporting manual differs on effective date, birth timing, or deadline")
        else:
            parser = VisibleText()
            parser.feed(path.read_text(encoding="utf-8"))
            text = compact(" ".join(parser.parts))
            for marker in WEB_MARKERS[filename]:
                require(marker in text, f"Missing public anchor {marker} in {filename}")
            if filename == "hira-research-catalog.html":
                require("출생통보" not in text and "RWN001" not in text, "The overview now names a birth product")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("retrieval_a", type=Path)
    parser.add_argument("retrieval_b", type=Path)
    args = parser.parse_args()
    expected = json.loads((HERE / "evidence.json").read_bytes())
    for index, directory in enumerate((args.retrieval_a, args.retrieval_b)):
        verify(directory, expected, index)
    print("Verified six frozen PDFs, four privacy register entries and five HTML sources in two downloads")
