"""Verify the four registered INEGI ZIPs and count observed birth years before selection."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

R10 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R10.parent / "r9/data/mexico"))
from audit_mexico2015 import dbf_rows


def audit(directory):
    decisions = json.loads((R10 / "source_decisions.json").read_text())
    slots = []
    for slot in decisions["source_slots"]:
        if slot.get("country") != "MX" or slot["status"] != "available":
            continue
        manifest = json.loads((R10 / "mexico/samples" / slot["id"] / "sampling_manifest.json").read_text())
        archives = []
        birth_year = slot["birth_year"]
        for year in slot["registration_archive_years"]:
            name = f"natalidad_base_datos_{year}_dbf.zip"
            path = directory / str(year) / name
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != manifest["archive_sha256"][str(year)]:
                raise ValueError(f"Archive differs from the freeze for registration year {year}")
            physical = active = matches = 0
            with ZipFile(path) as source:
                member = f"NACIM{str(year)[-2:]}.DBF"
                candidates = [s for s in source.namelist() if Path(s).name.upper() == member]
                if len(candidates) != 1:
                    raise ValueError(f"Expected one {member} table in {path.name}")
                for _, deleted, row in dbf_rows(source, candidates[0], ("ANO_NAC",)):
                    physical += 1
                    if not deleted:
                        active += 1
                        matches += row["ANO_NAC"] == str(birth_year)
            archives.append({
                "registration_year": year,
                "url": f"https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/{year}/{name}",
                "bytes": path.stat().st_size, "sha256": digest, "member": candidates[0],
                "physical_rows": physical, "active_rows": active, "active_target_birth_year_rows": matches,
            })
        total = sum(item["physical_rows"] for item in archives)
        matched = sum(item["active_target_birth_year_rows"] for item in archives)
        if total != slot["source_rows_audited"] or matched != slot["actual_birthyear_rows"]:
            raise ValueError(f"Published source/birth-year counts differ in {slot['id']}: {total}, {matched}")
        slots.append({"slot": slot["id"], "birth_year": birth_year, "archives": archives,
                      "source_rows": total, "target_birth_year_rows": matched})
    if len(slots) != 2:
        raise ValueError("Expected the two frozen Mexican source-year groups")
    return {"scope": "Original archives and birth-year denominators before eligibility and sampling.",
            "source_fields_read": ["DBF deletion flag", "ANO_NAC"], "slots": slots}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive_root", type=Path, help="Private root with one year/natalidad_base_datos_YEAR_dbf.zip per registration year")
    print(json.dumps(audit(cli.parse_args().archive_root), indent=2))
