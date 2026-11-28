"""Cross-check the two public catalogue representations of DANE birth variables."""

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import xml.etree.ElementTree as ET


class DictionaryLinks(HTMLParser):
    def __init__(self, file_id):
        super().__init__()
        self.file_id = file_id
        self.fields = []
        self.field = None

    def handle_starttag(self, tag, attributes):
        if tag != "a":
            return
        attrs = dict(attributes)
        if ("text-break" in attrs.get("class", "").split()
                and "var-id" in attrs.get("class", "").split()
                and f"/variable/{self.file_id}/" in attrs.get("href", "")):
            self.field = []

    def handle_data(self, value):
        if self.field is not None:
            self.field.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.field is not None:
            self.fields.append("".join(self.field).strip())
            self.field = None


def read_pair(directory, year, file_id):
    prefix = directory / f"col-{year}"
    parser = DictionaryLinks(file_id)
    parser.feed(prefix.with_suffix(".html").read_text(encoding="utf-8"))
    parser.close()
    xml = ET.parse(prefix.with_suffix(".xml"))
    file_descriptor = xml.find(f".//{{*}}fileDscr[@ID='{file_id}']")
    if file_descriptor is None:
        raise ValueError(f"Missing DDI file descriptor for {year}")
    catalogue_name = file_descriptor.findtext(".//{*}fileName", default="").strip()
    if str(year) not in catalogue_name:
        raise ValueError(f"Wrong DDI file for {year}")

    fields = {}
    for variable in xml.findall(".//{*}var"):
        if file_id in variable.get("files", "").split():
            name = variable.attrib["name"]
            if name in fields:
                raise ValueError(f"Duplicate DDI variable in {year}: {name}")
            fields[name] = " ".join(variable.findtext("{*}labl").split())
    if not fields or list(fields) != parser.fields:
        raise ValueError(f"DDI and HTML variable order differs for {year}")
    birth_fields = ["ANO", "MES", "SEXO", "COD_DPTO", "COD_MUNIC", "FECHA_NACM"]
    return {
        "file_id": file_id,
        "ddi_file_name": catalogue_name,
        "matching_ordered_variables": len(fields),
        "focus_labels": {name: fields[name] for name in birth_fields},
        "all_field_codes": list(fields),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_directory", type=Path)
    args = parser.parse_args()
    review = {str(year): read_pair(args.metadata_directory, year, file_id)
              for year, file_id in ((1999, "F11"), (2009, "F32"))}
    print(json.dumps(review, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
