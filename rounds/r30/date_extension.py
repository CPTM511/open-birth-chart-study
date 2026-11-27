"""Build the reviewed R30 extension of the birth-date validation limit."""

from pathlib import Path
import sys

from rounds.r27.archive_source import ROOT, digest, read_json, require


SOURCE = ROOT / "rounds/r10/methods/open_birth_chart_r10"
CHANGES = {
    "astronomy.py": (("civil.year <= 2025", "civil.year <= 2026"), ("1880–2025 range", "1880–2026 range")),
    "bazi_engine.py": (("civil.year <= 2025", "civil.year <= 2026"), ("1880–2025 scope", "1880–2026 scope")),
    "ziwei_bridge.cjs": (("y>2025", "y>2026"),),
}


def activate(directory: Path):
    target = directory / SOURCE.name
    target.mkdir(mode=0o700, parents=True)
    receipt = read_json(ROOT / "rounds/r10/public_methods_receipt.json")
    sealed = {ROOT / entry["path"]: entry["sha256"] for entry in receipt["files"] if (ROOT / entry["path"]).parent == SOURCE}
    require(set(sealed) == {path for path in SOURCE.iterdir() if path.is_file()}, "The frozen engine file list differs")
    outcomes = {}
    for src, original_hash in sorted(sealed.items()):
        require(digest(src) == original_hash, "A frozen engine file differs from the R10 seal")
        content = src.read_bytes()
        for old, new in CHANGES.get(src.name, ()):
            before = old.encode("utf-8")
            require(content.count(before) == 1, "A registered limit is missing or repeated")
            content = content.replace(before, new.encode("utf-8"))
        extended = target / src.name
        extended.write_bytes(content)
        changed_hash = digest(extended)
        if changed_hash != original_hash:
            outcomes[src.name] = {"before_sha256": original_hash, "after_sha256": changed_hash}
    require(set(outcomes) == set(CHANGES), "The extension changed a different set of frozen files")
    require(not any(name.startswith("open_birth_chart_r10") for name in sys.modules), "Load the extension before scoring")
    sys.path.insert(0, str(directory))
    return outcomes
