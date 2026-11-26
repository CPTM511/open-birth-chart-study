#!/usr/bin/env python3
"""Build birth-only R8 inputs from public source snapshots; never parse outcomes.

Only the Python standard library is required. Large archives stay in --raw-dir.
This script does not create global survey weights. Every weight is conditional on
one source's explicitly eligible frame. The two source samples remain separate.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, date, timedelta, timezone
from functools import lru_cache
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
from zoneinfo import ZoneInfo, TZPATH
import zipfile

SEED = "OBS-R8-2026-11-26"
UTC = timezone.utc
MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = MODULE_ROOT / "data" / "cache"
DEFAULT_OUTPUT = MODULE_ROOT / "data" / "reconstructed"
IBGE_URL = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip"
IANA_URL = "https://data.iana.org/time-zones/tzdb/southamerica"
BRAZIL_QUALITY = "official_clock_municipality_reference_iana"
OGDB_QUALITY = "source_clock_offset_consistent_locality_reference"
MODEL_KEYS = ("study_id", "birth_local", "birth_utc", "source_offset_seconds",
              "sex_resolved", "latitude", "longitude", "calendar",
              "time_precision_seconds", "time_uncertainty_seconds",
              "coordinate_precision_degrees", "timezone_id", "instant_scale")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def timezone_database_version():
    """Report the database used by zoneinfo without assuming an OS directory."""
    for root in TZPATH:
        candidate = Path(root) / "tzdata.zi"
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as f:
                return f.readline().strip()
    try:
        import tzdata
        return "# version " + tzdata.IANA_VERSION
    except (ImportError, AttributeError):
        return "unknown: system zoneinfo has no readable version marker"


def normalized(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.upper())
                   if unicodedata.category(c) != "Mn")


def timezone_for_municipality(uf, name):
    # Only areas explicitly identified by IANA are accepted in the two split
    # states. This is a deliberate coverage restriction, not an imputation.
    name = normalized(name)
    if uf == "13":
        if name in {"BOCA DO ACRE", "JUTAI", "MANAUS"}:
            return "America/Manaus", "IANA_explicit_named_municipality"
        if name in {"ATALAIA DO NORTE", "BENJAMIN CONSTANT", "EIRUNEPE", "ENVIRA", "IPIXUNA"}:
            return "America/Eirunepe", "IANA_explicit_named_municipality"
        return None, "unresolved_split_timezone_state"
    if uf == "15":
        if name in {"BELEM", "MARABA", "SAO FELIX DO XINGU"}:
            return "America/Belem", "IANA_explicit_named_municipality"
        if name in {"ALTAMIRA", "OBIDOS", "PRAINHA", "ORIXIMINA", "SANTAREM"}:
            return "America/Santarem", "IANA_explicit_named_municipality"
        return None, "unresolved_split_timezone_state"
    if uf == "26" and name == "FERNANDO DE NORONHA":
        return "America/Noronha", "IANA_explicit_island_exception"
    mapping = {
        "11": "America/Porto_Velho", "12": "America/Rio_Branco",
        "14": "America/Boa_Vista", "16": "America/Belem",
        "17": "America/Araguaina", "21": "America/Fortaleza",
        "22": "America/Fortaleza", "23": "America/Fortaleza",
        "24": "America/Fortaleza", "25": "America/Fortaleza",
        "26": "America/Recife", "27": "America/Maceio",
        "28": "America/Maceio", "29": "America/Bahia",
        "31": "America/Sao_Paulo", "32": "America/Sao_Paulo",
        "33": "America/Sao_Paulo", "35": "America/Sao_Paulo",
        "41": "America/Sao_Paulo", "42": "America/Sao_Paulo",
        "43": "America/Sao_Paulo", "50": "America/Campo_Grande",
        "51": "America/Cuiaba", "52": "America/Sao_Paulo",
        "53": "America/Sao_Paulo",
    }
    return mapping.get(uf), "IANA_named_state_group"


def municipality_references(raw_dir, out):
    gpkg = raw_dir / "ibge_2022.gpkg"
    if not gpkg.exists():
        with zipfile.ZipFile(raw_dir / "ibge_localities_2022.zip") as z:
            with z.open("BR_localidades_2022.gpkg") as src, gpkg.open("wb") as dst:
                for b in iter(lambda: src.read(1 << 20), b""):
                    dst.write(b)
    conn = sqlite3.connect(gpkg)
    rows = conn.execute("""SELECT CD_UF,SIGLA_UF,CD_MUN,NM_MUN,CT_LOCALIDADE,
        SCT_LOCALIDADE,LAT_LOCALIDADE,LONG_LOCALIDADE FROM BR_localidades_2022
        WHERE CT_LOCALIDADE IN ('Cidade','Distrito Estadual de Fernando de Noronha')
        ORDER BY CD_MUN, SCT_LOCALIDADE""").fetchall()
    conn.close()
    refs = {}
    duplicate_references = 0
    for uf, uf_name, code, name, kind, subkind, lat, lon in rows:
        code = str(code)
        short = code[:6]
        zone, zone_method = timezone_for_municipality(str(uf), name)
        ref = dict(municipality_ibge7=code, municipality_code=short,
                   municipality_name=name, state_code=str(uf), state=uf_name,
                   latitude=float(lat), longitude=float(lon), timezone_id=zone,
                   timezone_mapping_method=zone_method,
                   geo_precision="municipality_reference",
                   coordinate_reference_year=2022,
                   coordinate_reference_kind=kind, coordinate_reference_subkind=subkind,
                   coordinate_method="IBGE locality reference point of municipal seat; NOT birthplace/hospital point or polygon centroid",
                   coordinate_source=IBGE_URL)
        if short in refs:
            old = refs[short]
            assert old["municipality_ibge7"] == code, "Ambiguous 6-digit municipality prefix"
            assert abs(old["latitude"] - ref["latitude"]) < 1e-7 and abs(old["longitude"] - ref["longitude"]) < 1e-7, "Conflicting municipal references"
            duplicate_references += 1
        else:
            refs[short] = ref
    write_json(out / "audits/municipality_reference_audit.json", {
        "source": IBGE_URL, "reference_year": 2022, "selected_point_rows": len(rows),
        "distinct_municipality_prefixes": len(refs),
        "identical_capital_and_seat_duplicates_collapsed": duplicate_references,
        "zone_mapped_municipalities": sum(r["timezone_id"] is not None for r in refs.values()),
        "temporal_limitation": "2022 municipal-seat reference points are approximate locators for 2006 births; unmatched historical codes are excluded.",
        "split_state_policy": "In Amazonas and Para only modern municipalities explicitly named in IANA southamerica are assigned a zone. Other municipalities are excluded, not guessed.",
        "timezone_source": IANA_URL,
    })
    write_json(out / "reference/ibge_municipality_reference.json", refs)
    return refs


@lru_cache(maxsize=None)
def zone_obj(name):
    return ZoneInfo(name)


def valid_offsets(local, zone):
    z = zone_obj(zone)
    offsets = set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=z, fold=fold)
        utc = aware.astimezone(UTC)
        if utc.astimezone(z).replace(tzinfo=None) == local:
            offsets.add(int(aware.utcoffset().total_seconds()))
    return tuple(sorted(offsets))


@lru_cache(maxsize=200000)
def hourly_offsets(zone, y, m, d, h):
    # Brazil's 2006 IANA transitions occur on hour boundaries. Verify both ends
    # of each encountered civil hour; fall back to exact minute when they differ.
    a = valid_offsets(datetime(y, m, d, h, 0), zone)
    b = valid_offsets(datetime(y, m, d, h, 59, 59), zone)
    return a if a == b else None


def row_offset(local, zone):
    possible = hourly_offsets(zone, local.year, local.month, local.day, local.hour)
    if possible is None:
        possible = valid_offsets(local, zone)
    return possible


@lru_cache(maxsize=1000)
def brazil_date(s):
    if not re.fullmatch(r"[0-9]{8}", s):
        return None
    try:
        return date(int(s[4:]), int(s[2:4]), int(s[:2]))
    except ValueError:
        return None


def brazil_rows(raw_dir):
    with zipfile.ZipFile(raw_dir / "brazil2006.zip") as z:
        with z.open("DNBR2006.csv") as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
            header = next(reader)
            indices = [header.index(x) for x in ["contador", "DTNASC", "HORANASC", "SEXO", "CODMUNNASC"]]
            for ordinal, row in enumerate(reader, 1):
                yield (str(ordinal),) + tuple(row[i] for i in indices)


class IdSeen:
    """Efficient source-ID duplicate check, without deduplicating twins."""
    def __init__(self):
        self.bits = bytearray()
        self.other = set()

    def add_duplicate(self, source_id):
        if source_id.isdigit() and 0 <= int(source_id) <= 100_000_000:
            n = int(source_id)
            pos, bit = divmod(n, 8)
            if pos >= len(self.bits):
                self.bits.extend(b"\0" * (pos + 1 - len(self.bits)))
            mask = 1 << bit
            exists = bool(self.bits[pos] & mask)
            self.bits[pos] |= mask
            return exists
        exists = source_id in self.other
        self.other.add(source_id)
        return exists


def brazil_eligible(raw_dir, refs, audit=None):
    seen = IdSeen()
    for row_id, record_counter, ds, ts, sex_code, mun in brazil_rows(raw_dir):
        if audit is not None:
            audit["counts"]["raw_rows"] += 1
            # `contador` restarts within this national export and is NOT a
            # globally unique person ID. Retain every source row and use its
            # physical archive ordinal as stable record ID; never dedup twins.
            if seen.add_duplicate(record_counter):
                audit["counts"]["repeated_counter_value_not_removed"] += 1
        dd = brazil_date(ds)
        valid_date = dd is not None and dd.year == 2006
        valid_time = len(ts) == 4 and ts.isascii() and ts.isdigit() and int(ts[:2]) < 24 and int(ts[2:]) < 60
        valid_sex = sex_code in ("1", "2")
        valid_mun = len(mun) == 6 and mun.isascii() and mun.isdigit()
        if audit is not None:
            for name, ok in [("date_2006", valid_date), ("clock_HHMM", valid_time), ("sex_MF", valid_sex), ("municipality_code", valid_mun)]:
                if not ok:
                    audit["invalid_field_nonexclusive"][name] += 1
        if not (valid_date and valid_time and valid_sex and valid_mun):
            if audit is not None:
                audit["excluded"]["incomplete_or_invalid_birth_fields"] += 1
            continue
        sex = "M" if sex_code == "1" else "F"
        if audit is not None:
            audit["counts"]["complete_date_clock_sex_municipality"] += 1
            audit["field_complete_by_uf_sex"][mun[:2] + "|" + sex] += 1
            audit["minute_mod5_field_complete"][int(ts[2:]) % 5] += 1
        ref = refs.get(mun)
        if ref is None:
            if audit is not None:
                audit["excluded"]["unmatched_historical_municipality_code"] += 1
                audit["unmatched_municipality_codes"][mun] += 1
            continue
        if audit is not None:
            audit["counts"]["complete_with_reference_coordinates"] += 1
        zone = ref["timezone_id"]
        if zone is None:
            if audit is not None:
                audit["excluded"]["unresolved_split_state_timezone"] += 1
                audit["unresolved_timezone_by_uf"][mun[:2]] += 1
            continue
        local = datetime(dd.year, dd.month, dd.day, int(ts[:2]), int(ts[2:]))
        offsets = row_offset(local, zone)
        if len(offsets) != 1:
            if audit is not None:
                reason = "nonexistent_civil_clock_DST_gap" if len(offsets) == 0 else "ambiguous_civil_clock_DST_fold"
                audit["excluded"][reason] += 1
                audit["dst_exclusions_by_zone_date"][f"{reason}|{zone}|{dd.isoformat()}"] += 1
            continue
        stratum = f"BR|{mun[:2]}|{sex}|2000|{BRAZIL_QUALITY}"
        if audit is not None:
            audit["counts"]["four_system_birth_input_eligible"] += 1
            audit["eligible_by_uf_sex"][mun[:2] + "|" + sex] += 1
            audit["eligible_strata"][stratum] += 1
        yield row_id, local, sex, mun, offsets[0], stratum, record_counter


def proportional_quotas(counts, max_n):
    total = sum(counts.values())
    target = min(total, max_n)
    if total <= max_n:
        return dict(counts)
    if len(counts) > target:
        raise ValueError("Cannot give each nonempty stratum one sample")
    ideal = {h: target * n / total for h, n in counts.items()}
    q = {h: min(n, max(1, math.floor(ideal[h]))) for h, n in counts.items()}
    # Deterministic ties use the full stratum string.
    while sum(q.values()) > target:
        h = sorted((h for h in q if q[h] > 1), key=lambda h: (q[h] - ideal[h], h), reverse=True)[0]
        q[h] -= 1
    for h in sorted(q, key=lambda h: (-(ideal[h] - q[h]), h)):
        if sum(q.values()) == target:
            break
        if q[h] < counts[h]:
            q[h] += 1
    assert sum(q.values()) == target
    return q


def sampling_hash(source_id):
    return hashlib.sha256((SEED + "|" + source_id).encode()).hexdigest()


def study_id(source_id):
    return "R8-" + hashlib.sha256(source_id.encode()).hexdigest()[:24]


def weight_metadata(stratum, counts, quotas):
    n, k = counts[stratum], quotas[stratum]
    return dict(stratum_id=stratum, N_h=n, n_h=k,
                inclusion_probability=k / n, sample_weight=n / k,
                weight_scope="eligible_source_frame_only")


def write_rows(out, source, rows, counts, quotas):
    sample = out / "samples" / source
    sample.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: r["study_id"])
    full_path = sample / "birth_metadata.jsonl"
    model_path = sample / "birth_inputs.jsonl"
    with full_path.open("w") as full, model_path.open("w") as model:
        for r in rows:
            full.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            model.write(json.dumps({k: r.get(k) for k in MODEL_KEYS}, separators=(",", ":")) + "\n")
    allocations = [dict(stratum_id=h, N_h=counts[h], n_h=quotas[h],
                        inclusion_probability=quotas[h] / counts[h], sample_weight=counts[h] / quotas[h])
                   for h in sorted(counts)]
    write_json(sample / "sampling_manifest.json", {
        "source": source, "seed": SEED, "eligible_frame_N": sum(counts.values()),
        "sample_n": len(rows), "algorithm": "minimum 1 per nonempty stratum; proportional floor quotas and largest remainders; SHA256(seed+'|'+source_id) ascending within stratum",
        "stratum_fields": "country / Brazil UF × explicit sex × birth decade × quality",
        "strata": allocations, "model_input_sha256": sha256(model_path),
        "metadata_sha256": sha256(full_path),
        "weight_interpretation": "Conditional inclusion probabilities for this source's eligible records. They are not weights for national registered births outside eligibility, all births, or the global population.",
        "outcome_fields": [], "selection_uses_model_outputs": False,
    })
    return {"source": source, "eligible_N": sum(counts.values()), "sample_n": len(rows),
            "birth_inputs": str(model_path), "sha256": sha256(model_path)}


def build_brazil(raw_dir, out, refs, max_n):
    audit = {k: Counter() for k in ["counts", "excluded", "invalid_field_nonexclusive",
        "field_complete_by_uf_sex", "minute_mod5_field_complete", "eligible_by_uf_sex",
        "eligible_strata", "unmatched_municipality_codes", "unresolved_timezone_by_uf",
        "dst_exclusions_by_zone_date"]}
    for _ in brazil_eligible(raw_dir, refs, audit):
        pass
    counts = audit["eligible_strata"]
    quotas = proportional_quotas(counts, max_n)
    print(json.dumps({"stage": "brazil_frame_complete", "counts": audit["counts"], "exclusions": audit["excluded"]}), flush=True)
    write_json(out / "audits/brazil2006_final_audit.json", audit)
    heaps = defaultdict(list)
    for row in brazil_eligible(raw_dir, refs):
        row_id, local, sex, mun, offset, stratum, record_counter = row
        source_id = "SINASC2006:row:" + row_id.zfill(7)
        rank = int(sampling_hash(source_id), 16)
        heap = heaps[stratum]
        item = (-rank, source_id, row)
        if len(heap) < quotas[stratum]:
            heapq.heappush(heap, item)
        elif rank < -heap[0][0]:
            heapq.heapreplace(heap, item)
    output_rows = []
    for stratum, heap in heaps.items():
        for neg_rank, source_id, row in heap:
            row_id, local, sex, mun, offset, _, record_counter = row
            ref = refs[mun]
            r = dict(study_id=study_id(source_id), source_id=source_id, source="SINASC-2006",
                source_row_id=row_id, source_record_counter=record_counter, birth_local=local.isoformat(),
                birth_utc=(local - timedelta(seconds=offset)).isoformat() + "Z",
                source_offset_seconds=offset, utc_offset_seconds=offset,
                utc_offset_hours=offset / 3600, sex_resolved=sex, sex=sex,
                birth_country="BR", birth_year=2006, birth_decade=2000,
                calendar="gregorian", instant_scale="UT", time_precision_seconds=60,
                time_uncertainty_seconds=None, coordinate_precision_degrees=None,
                clock_precision="source_display_minutes; measurement_error_unknown",
                quality=BRAZIL_QUALITY, sampling_sha256=f"{-neg_rank:064x}",
                uncertainty_flags=["municipal_seat_not_actual_birthplace_point",
                    "2022_coordinate_reference_for_2006_birth", "clock_accuracy_not_independently_verified"],
                timezone_source=IANA_URL, **ref,
                **weight_metadata(stratum, counts, quotas))
            output_rows.append(r)
    return write_rows(out, "brazil2006", output_rows, counts, quotas)


def pg_copy_unescape(s):
    """Decode PostgreSQL COPY-text escaping exactly once, without Unicode damage."""
    mapping = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
    def replace(m):
        value = m.group(1)
        if value.startswith("x") and len(value) > 1:
            return chr(int(value[1:], 16))
        if value[0] in "01234567":
            return chr(int(value, 8))
        return mapping.get(value, value)
    return re.sub(r"\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)", replace, s)


def pg_birth_rows(raw_dir):
    active = False
    with zipfile.ZipFile(raw_dir / "ogdb_pg_dump.zip") as z:
        with z.open("ogdb-pg-dump") as f:
            for raw in f:
                if not active:
                    if raw.startswith(b"COPY public.person "):
                        header = raw.decode()
                        expected = "(id, slug, ids_in_sources, partial_ids, name, sex, birth, death, occus, trust, acts, history, notes)"
                        assert expected in header, "Source schema changed"
                        active = True
                    continue
                if raw.rstrip(b"\r\n") == b"\\.":
                    break
                fields = raw.decode("utf-8").rstrip("\r\n").split("\t")
                # Deliberate whitelist: do not parse names, outcomes, history,
                # occupations, notes, or any other columns.
                yield fields[0], fields[5], fields[6]


def parse_tzo(s):
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})(?::(\d{2}))?", s or "")
    if not m:
        raise ValueError("Missing or unsupported offset")
    hh, mm, ss = int(m[2]), int(m[3]), int(m[4] or 0)
    if hh > 14 or mm > 59 or ss > 59:
        raise ValueError("Out-of-range offset")
    return (1 if m[1] == "+" else -1) * (hh * 3600 + mm * 60 + ss)


def parse_explicit_clock(s):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?", s):
        raise ValueError("Date lacks explicit unambiguous clock")
    return datetime.fromisoformat(s)


def build_ogdb(raw_dir, out, max_n):
    audit = {k: Counter() for k in ["counts", "excluded", "sex_raw", "eligible_countries", "eligible_decades", "eligible_strata", "minute_mod5_eligible", "offset_residual_seconds"]}
    eligible = []
    seen = set()
    for row_id, sex, birth_raw in pg_birth_rows(raw_dir):
        audit["counts"]["raw_person_records"] += 1
        audit["sex_raw"][sex] += 1
        if row_id in seen:
            audit["excluded"]["duplicate_source_id"] += 1
            continue
        seen.add(row_id)
        try:
            b = json.loads(pg_copy_unescape(birth_raw))
        except Exception:
            audit["excluded"]["birth_json_parse_error"] += 1
            continue
        p = b.get("place") or {}
        try:
            local = parse_explicit_clock(b.get("date"))
            utc = parse_explicit_clock(b.get("date-ut"))
            offset = parse_tzo(b.get("tzo"))
            lat, lon = float(p["lat"]), float(p["lg"])
            assert math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
            assert (lat, lon) != (0.0, 0.0)
        except (ValueError, TypeError, KeyError, AssertionError):
            audit["excluded"]["missing_invalid_clock_offset_or_coordinate"] += 1
            continue
        audit["counts"]["complete_clock_offset_coordinate_any_sex"] += 1
        if sex not in {"M", "F"}:
            audit["excluded"]["missing_or_other_sex"] += 1
            continue
        audit["counts"]["complete_clock_offset_coordinate_explicit_MF"] += 1
        if not 1880 <= local.year <= 1979:
            audit["excluded"]["outside_historical_window_1880_1979"] += 1
            continue
        audit["counts"]["historical_complete_fields_before_offset_consistency"] += 1
        residual = int((local - utc).total_seconds()) - offset
        if abs(residual) > 1:
            audit["excluded"]["local_UTC_offset_conflict_gt_1_second"] += 1
            continue
        # Source-specific sign error visible in some raw records; excluded rather
        # than corrected. Most such rows also lack an offset and fail above.
        if normalized(str(p.get("name", ""))) == "PARIS" and p.get("cy") == "FR" and lon < 0:
            audit["excluded"]["known_Paris_longitude_sign_conflict"] += 1
            continue
        country = p.get("cy")
        if not isinstance(country, str) or not re.fullmatch("[A-Z]{2}", country):
            audit["excluded"]["missing_country_for_stratification"] += 1
            continue
        source_id = "OGDB2023:" + row_id
        decade = (local.year // 10) * 10
        stratum = f"{country}|{sex}|{decade}|{OGDB_QUALITY}"
        audit["counts"]["four_system_birth_input_eligible"] += 1
        audit["eligible_countries"][country] += 1
        audit["eligible_decades"][decade] += 1
        audit["eligible_strata"][stratum] += 1
        audit["minute_mod5_eligible"][local.minute % 5] += 1
        audit["offset_residual_seconds"][residual] += 1
        r = dict(study_id=study_id(source_id), source_id=source_id, source="OGDB-2023-08-20",
            source_row_id=row_id, birth_local=local.isoformat(), birth_utc=utc.isoformat() + "Z",
            source_offset_seconds=offset, utc_offset_seconds=offset, utc_offset_hours=offset / 3600,
            sex_resolved=sex, sex=sex, birth_country=country, birth_year=local.year, birth_decade=decade,
            calendar="gregorian", instant_scale="UT", latitude=lat, longitude=lon,
            timezone_id=None, timezone_method="source_explicit_historical_offset_not_independently_verified",
            time_precision_seconds=1 if len(b["date"]) == 19 else 60, time_uncertainty_seconds=None,
            coordinate_precision_degrees=None, geo_precision="source_locality_reference",
            clock_precision="source_display_resolution_only; measurement_error_unknown",
            quality=OGDB_QUALITY, source_locality=p.get("name"), source_geoid=p.get("geoid"),
            source_utc_offset_residual_seconds=residual,
            sampling_sha256=sampling_hash(source_id),
            uncertainty_flags=["locality_coordinate_not_independently_verified",
                "historical_offset_not_independently_verified", "birth_clock_accuracy_unknown",
                "strong_source_selection_and_sex_completeness_bias"],
            stratum_id=stratum)
        eligible.append(r)
    counts = audit["eligible_strata"]
    quotas = proportional_quotas(counts, max_n)
    groups = defaultdict(list)
    for r in eligible:
        groups[r["stratum_id"]].append(r)
    rows = []
    for h, records in groups.items():
        records.sort(key=lambda r: r["sampling_sha256"])
        for r in records[:quotas[h]]:
            r.update(weight_metadata(h, counts, quotas))
            rows.append(r)
    audit["counts"]["birth_JSON_parsed"] = audit["counts"]["raw_person_records"] - audit["excluded"]["birth_json_parse_error"]
    audit["deduplication"] = {"unit": "public.person numeric primary ID", "same_birth_tuple_removed": False,
        "limitation": "No cross-source identity linkage and no name-based deduplication were performed; legitimate identical birth timestamps may exist."}
    write_json(out / "audits/ogdb_final_audit.json", audit)
    print(json.dumps({"stage": "ogdb_frame_complete", "counts": audit["counts"], "countries": audit["eligible_countries"]}), flush=True)
    return write_rows(out, "ogdb2023", rows, counts, quotas)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", "--input-dir", type=Path, default=DEFAULT_CACHE,
                   help="Directory holding the pinned input ZIPs (default: data_expansion/data/cache)")
    p.add_argument("--output", "--output-dir", type=Path, default=DEFAULT_OUTPUT,
                   help="Directory for locally generated cohorts and audits (default: data_expansion/data/reconstructed)")
    p.add_argument("--max-n", type=int, default=2000)
    p.add_argument("--source", choices=["all", "brazil", "ogdb"], default="all")
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    results = []
    if a.source in {"all", "ogdb"}:
        results.append(build_ogdb(a.raw_dir, a.output, a.max_n))
    if a.source in {"all", "brazil"}:
        refs = municipality_references(a.raw_dir, a.output)
        results.append(build_brazil(a.raw_dir, a.output, refs, a.max_n))
    tz_version = timezone_database_version()
    write_json(a.output / ("build_manifest.json" if a.source == "all" else f"{a.source}_build_manifest.json"), {
        "built_utc": datetime.now(UTC).isoformat(), "sampling_seed": SEED,
        "maximum_per_source": a.max_n, "tzdb": tz_version,
        "input_archive_sha256": {name: sha256(a.raw_dir / name) for name in
            ["brazil2006.zip", "ogdb_pg_dump.zip", "ibge_localities_2022.zip"] if (a.raw_dir / name).exists()},
        "outputs": results, "analysis_results_seen_by_builder": False,
        "death_or_other_outcomes_parsed": False,
        "global_representative_sampling_claim": False,
        "primary_input_precision": "Minute/second fields describe display resolution only. Neither clock accuracy nor exact birthplace coordinates were independently certified.",
    })
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
