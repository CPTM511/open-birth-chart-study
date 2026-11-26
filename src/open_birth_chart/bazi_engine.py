# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registered Bazi calculation and structural-signal engine.

The complete exported calculation pipeline is not a complete traditional
interpretive doctrine. Scores are structural counts, never event probabilities.
Pinned runtime: lunar-python==1.4.9. No outcomes or network calls are accepted.
"""
from __future__ import annotations
from calendar import monthrange
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
import math
from lunar_python import Solar
from lunar_python.util import LunarUtil

VERSION = "OBS-R8-BZ-1.0"
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
ELEMENTS = "木火土金水"
JIAZI = tuple(GAN[i % 10] + ZHI[i % 12] for i in range(60))
GROWTH = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")
GROWTH_START = {"甲": 11, "乙": 6, "丙": 2, "丁": 9, "戊": 2, "己": 9, "庚": 5, "辛": 0, "壬": 8, "癸": 3}
HARMONY = {frozenset(x) for x in ["子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"]}
HARM = {frozenset(x) for x in ["子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"]}
TRINES = {"water": "申子辰", "wood": "亥卯未", "fire": "寅午戌", "metal": "巳酉丑"}
CST = timezone(timedelta(hours=8))
UTC = timezone.utc


class InputError(ValueError):
    """A missing or contradictory birth field, not a negative signal."""


def _solar(dt):
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _datetime_solar(s):
    return datetime(s.getYear(), s.getMonth(), s.getDay(), s.getHour(), s.getMinute(), s.getSecond())


def _years(dt, n):
    year = dt.year + n
    return dt.replace(year=year, day=min(dt.day, monthrange(year, dt.month)[1]))


def normalize_birth(row, shift_minutes=0):
    """Resolve existing civil/instant labels; never infer a zone from a country."""
    if not isinstance(row, dict):
        raise InputError("Birth input must be an object")
    if str(row.get("calendar", "gregorian")).lower() != "gregorian":
        raise InputError("An explicit Gregorian input is required")
    try:
        civil = datetime.fromisoformat(row["birth_local"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("Complete local date and clock required") from exc
    if "T" not in row["birth_local"] and " " not in row["birth_local"]:
        raise InputError("Date without a clock is not eligible")
    if civil.tzinfo is not None:
        raise InputError("birth_local must be a clock label without offset")
    if not 1880 <= civil.year <= 2019:
        raise InputError("Birth year outside the frozen 1880–2019 scope")
    sex = row.get("sex", row.get("sex_resolved"))
    if sex not in ("M", "F"):
        raise InputError("Traditional cycle direction requires recorded M/F")
    raw_offset = row.get("source_offset_seconds", row.get("utc_offset_seconds"))
    if raw_offset is None and row.get("timezone_offset_minutes") is not None:
        raw_offset = float(row["timezone_offset_minutes"]) * 60
    if raw_offset is not None:
        if isinstance(raw_offset, bool) or not math.isfinite(float(raw_offset)) or abs(float(raw_offset)) >= 86400:
            raise InputError("Invalid source clock offset")
        offset = float(raw_offset)
    else:
        offset = None
    absolute = None
    if row.get("birth_utc") is not None:
        try:
            absolute = datetime.fromisoformat(row["birth_utc"].replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise InputError("Invalid nominal UTC/UT1 label") from exc
        if absolute.tzinfo is None:
            absolute = absolute.replace(tzinfo=UTC)
        if absolute.utcoffset() != timedelta(0):
            raise InputError("birth_utc must have zero offset")
        implied = (civil - absolute.replace(tzinfo=None)).total_seconds()
        if offset is None:
            offset = implied  # derived from two supplied exact labels, never from place
        elif abs(implied - offset) > 1:
            raise InputError("Civil/instant/offset disagreement exceeds one second")
    elif offset is not None:
        absolute = (civil - timedelta(seconds=offset)).replace(tzinfo=UTC)
    else:
        raise InputError("A source instant or source offset is required for solar terms")
    if abs(offset) >= 86400:
        raise InputError("Supplied instant implies invalid offset")
    if not isinstance(shift_minutes, (int, float)) or not math.isfinite(shift_minutes):
        raise InputError("Invalid clock perturbation")
    delta = timedelta(minutes=shift_minutes)
    return {"civil": civil + delta, "absolute": absolute + delta, "offset": offset, "sex": sex,
            "study_id": str(row.get("study_id", "")), "shift_minutes": shift_minutes}


def element(stem):
    return LunarUtil.WU_XING_GAN[stem]


def control(a, b):
    return (ELEMENTS.index(element(a)) + 2) % 5 == ELEMENTS.index(element(b))


def stem_combines(a, b):
    return a != b and abs(GAN.index(a) - GAN.index(b)) == 5


def branch_clashes(a, b):
    return (ZHI.index(a) - ZHI.index(b)) % 12 == 6


def growth(day_stem, branch):
    step = 1 if GAN.index(day_stem) % 2 == 0 else -1
    return GROWTH[((ZHI.index(branch) - GROWTH_START[day_stem]) * step) % 12]


def describe_pillar(ganzhi, day_stem):
    hidden = LunarUtil.ZHI_HIDE_GAN[ganzhi[1]]
    return {"ganzhi": ganzhi, "stem": ganzhi[0], "branch": ganzhi[1],
            "stem_element": element(ganzhi[0]), "branch_element": LunarUtil.WU_XING_ZHI[ganzhi[1]],
            "stem_ten_god": LunarUtil.SHI_SHEN[day_stem + ganzhi[0]],
            "hidden_stems": [{"stem": h, "element": element(h), "ten_god": LunarUtil.SHI_SHEN[day_stem + h]} for h in hidden],
            "nayin": LunarUtil.NAYIN.get(ganzhi), "growth_phase_for_day_master": growth(day_stem, ganzhi[1]),
            "xun": LunarUtil.getXun(ganzhi), "xunkong": LunarUtil.getXunKong(ganzhi)}


def relation(a, b):
    ba, bb = a[1], b[1]
    clash = branch_clashes(ba, bb)
    controlled = control(a[0], b[0]) or control(b[0], a[0])
    harmony = frozenset((ba, bb)) in HARMONY
    stems_he = stem_combines(a[0], b[0])
    return {"branch_clash": clash, "branch_harmony": harmony, "branch_harm": frozenset((ba, bb)) in HARM,
            "stem_control_either_direction": controlled, "stem_control_a_to_b": control(a[0], b[0]),
            "stem_combination": stems_he, "stem_control_branch_clash": clash and controlled,
            "stem_and_branch_combination": harmony and stems_he, "repeated_pillar": a == b}


def group_patterns(branches):
    counts = Counter(branches);present = set(branches)
    return {"complete_three_harmonies": [label for label, bs in TRINES.items() if set(bs) <= present],
            "complete_three_punishments": [bs for bs in ["寅巳申", "丑戌未"] if set(bs) <= present],
            "zi_mao_punishment": set("子卯") <= present,
            "self_punishments": [b for b in "辰午酉亥" if counts[b] >= 2],
            "transformation_adjudicated": False}


def interpret_pillars(natal, contextual_pillars=None):
    """Bounded, source-linked month-command clauses with explicit unknowns.

    No weighted score below is used to decide classical strength. Contextual
    pillars are luck-period inputs, never a replacement natal month command.
    """
    dm = natal["day"][0]
    month = natal["month"][1]
    natal_visible = [v[0] for k,v in natal.items() if k != "day"]
    hidden = LunarUtil.ZHI_HIDE_GAN[month]
    exposed_hidden = list(dict.fromkeys(h for h in hidden if h in natal_visible))
    trines = [bs for bs in TRINES.values() if month in bs and set(bs) <= {p[1] for p in natal.values()}]
    chosen = hidden[0] if month in "子午卯酉" or not exposed_hidden else exposed_hidden[0] if len(exposed_hidden) == 1 else None
    selection_status = "base_month_candidate" if chosen else "competing_exposed_candidates"
    if trines:selection_status = "transformation_premises_require_adjudication"
    base_god = LunarUtil.SHI_SHEN[dm + chosen] if chosen else None
    blade = GAN.index(dm) % 2 == 0 and growth(dm,month) == "帝旺"
    peer = base_god in {"比肩","劫财"}
    pattern = "阳刃" if blade else "建禄月劫" if peer else base_god
    stable_pattern = chosen is not None and not trines
    visible = natal_visible + [p[0] for p in (contextual_pillars or {}).values()]
    gods = Counter(LunarUtil.SHI_SHEN[dm+s] for s in visible)
    branches = [p[1] for p in natal.values()]
    roots = []
    for key,p in natal.items():
        same = [s for s in LunarUtil.ZHI_HIDE_GAN[p[1]] if element(s) == element(dm)]
        phase = growth(dm,p[1])
        heavy = phase in {"临官","帝旺"} or GAN.index(dm)%2 == 0 and phase == "长生"
        if same or heavy:roots.append({"pillar":key,"branch":p[1],"same_element_hidden_stems":same,"growth_phase":phase,"heavy_root_clause":heavy})
    strength = {"month_main_element":element(hidden[0]),"day_element":element(dm),
                "same_element_in_month_main_qi":element(hidden[0])==element(dm),
                "roots":roots,"visible_peer_count":gods["比肩"]+gods["劫财"],
                "visible_resource_count":gods["正印"]+gods["偏印"],
                "classical_strong_weak_verdict":None,
                "reason":"Season alone is insufficient; root evidence is exposed without an invented numerical strength verdict."}
    wealth = bool(gods["正财"]+gods["偏财"])
    resource = bool(gods["正印"]+gods["偏印"])
    officer,kill,food,hurt,rob = (bool(gods[g]) for g in ["正官","七杀","食神","伤官","劫财"])
    month_clashes = [k for k,p in natal.items() if k!="month" and branch_clashes(month,p[1])]
    patterns = group_patterns(branches)
    harm_or_break = any(frozenset((month,p[1])) in HARM or frozenset((month,p[1])) in {frozenset(x) for x in ["子酉","卯午","辰丑","戌未","寅亥","巳申"]} for k,p in natal.items() if k!="month")
    observed_damage = bool(month_clashes or harm_or_break or patterns["complete_three_punishments"] or patterns["self_punishments"] or patterns["zi_mao_punishment"])
    clauses=[]
    def emit(code,label,match,unresolved=()):
        clauses.append({"rule":code,"classification":label,"structural_match":bool(match),
                        "applicable_pattern_unambiguous":stable_pattern,"unresolved_premises":list(unresolved),
                        "final_life_outcome_inferred":False})
    emit("BZC01","officer_formation_context",pattern=="正官" and (wealth or resource) and not hurt and not observed_damage,["relative strength and effective placement"])
    emit("BZC02a","officer_hurting_officer_damage",pattern=="正官" and hurt)
    emit("BZC02b","resource_rescue_candidate",pattern=="正官" and hurt and resource,["resource effectiveness and combination order"])
    emit("BZC03","wealth_robbery_rescue_candidate",pattern in {"正财","偏财"} and rob and (food or officer),["effective mediation or control"])
    emit("BZC04a","eating_god_indirect_resource_damage",pattern=="食神" and bool(gods["偏印"]))
    emit("BZC04b","wealth_protects_food_candidate",pattern=="食神" and bool(gods["偏印"]) and wealth,["effective control and placement"])
    emit("BZC05a","food_controls_killings_candidate",pattern=="七杀" and food,["body and food strength"])
    emit("BZC05b","resource_interferes_with_food_control",pattern=="七杀" and food and resource,["effective resource/food relation"])
    emit("BZC05c","wealth_removes_resource_candidate",pattern=="七杀" and food and resource and wealth,["effective finance/resource placement"])
    emit("BZC06a","hurting_officer_meets_officer",pattern=="伤官" and officer and element(dm)!="金",["climate and special-pattern exceptions"])
    emit("BZC06b","hurting_officer_resource_or_wealth_context",pattern=="伤官" and (resource or wealth),["relative strength; mediation not guaranteed"])
    emit("BZC07a","blade_without_officer_or_killings",pattern=="阳刃" and not (officer or kill))
    emit("BZC07b","blade_containment_formation_context",pattern=="阳刃" and (officer or kill) and (wealth or resource) and not hurt,["effective control and relative strength"])
    emit("BZC08","peer_command_formation_context",pattern=="建禄月劫" and ((officer and (wealth or resource)) or (wealth and (food or hurt)) or (kill and food)),["selection of the effective external use-god"])
    clash_rescues=[]
    for other in month_clashes:
        branch=natal[other][1]
        candidates=[k for k,p in natal.items() if k not in {"month",other} and (frozenset((month,p[1])) in HARMONY or frozenset((branch,p[1])) in HARMONY)]
        full_trines=[label for label,bs in TRINES.items() if (month in bs or branch in bs) and set(bs)<=set(branches)]
        clash_rescues.append({"clashing_pillar":other,"harmony_candidate_pillars":candidates,"full_trine_context":full_trines,"clash_automatically_removed":False,"reason":"Competing unions and placement can reverse rescue; preserve unresolved order."})
    return {"version":"OBS-R8-BZ-CLAUSES-1.0","source":"Gengcunji/Ziping month-command chapters",
            "strength_evidence":strength,"month_command":{"base_hidden_stem":hidden[0],"exposed_candidates":exposed_hidden,"selected_candidate":chosen,
                "candidate_ten_god":base_god,"pattern_candidate":pattern,"selection_status":selection_status,
                "month_in_complete_trines":trines,"yongshen_definition":"month-command functional role, not a universally favorable balancing element",
                "unique_month_candidate_under_registered_selector":stable_pattern and not peer and not blade,
                "unique_yongshen_adjudicated":False},
            "clause_matches":clauses,"month_clash_rescue_context":clash_rescues,
            "contextual_pillars":contextual_pillars or {},"net_fortune_verdict":None,"complete_traditional_interpretation":False}


def build_chart(row, shift_minutes=0):
    r = normalize_birth(row, shift_minutes)
    civil, instant = r["civil"], r["absolute"]
    cst = instant.astimezone(CST).replace(tzinfo=None)
    season_ec = _solar(cst).getLunar().getEightChar();season_ec.setSect(1)
    clock_ec = _solar(civil).getLunar().getEightChar();clock_ec.setSect(1)
    raw = {"year": season_ec.getYear(), "month": season_ec.getMonth(), "day": clock_ec.getDay(), "hour": clock_ec.getTime()}
    dm = raw["day"][0]
    pillars = {k: describe_pillar(v, dm) for k, v in raw.items()}
    yun = season_ec.getYun(1 if r["sex"] == "M" else 0, 2)
    start_cst = _datetime_solar(yun.getStartSolar())
    start_utc = start_cst.replace(tzinfo=CST).astimezone(UTC)
    # Decades start on exact qiyun anniversaries; lunar-python getDaYun exposes
    # year bins only, so intervals are built explicitly from its full start time.
    month_index = JIAZI.index(raw["month"])
    direction = 1 if yun.isForward() else -1
    periods = []
    for n in range(1, 25):
        begin_cst, end_cst = _years(start_cst, 10 * (n-1)), _years(start_cst, 10*n)
        periods.append({"index": n, "ganzhi": JIAZI[(month_index + direction*n) % 60],
                        "start_utc": begin_cst.replace(tzinfo=CST).astimezone(UTC).isoformat(),
                        "end_utc_exclusive": end_cst.replace(tzinfo=CST).astimezone(UTC).isoformat()})
    weights = Counter({e: 0.0 for e in ELEMENTS})
    for k, p in pillars.items():
        weights[p["stem_element"]] += 1
        scale = 2 if k == "month" else 1
        for h in p["hidden_stems"]:
            weights[h["element"]] += scale / len(p["hidden_stems"])
    dm_i = ELEMENTS.index(element(dm)); supportive = {ELEMENTS[dm_i], ELEMENTS[(dm_i-1) % 5]}
    support = sum(v for k, v in weights.items() if k in supportive) / sum(weights.values())
    main_hidden = pillars["month"]["hidden_stems"][0]
    natal_relations = [{"a": a, "b": b, **relation(raw[a], raw[b])} for a,b in combinations(raw,2)]
    return {"engine": VERSION, "status": "computed_for_registered_conventions", "study_id": r["study_id"],
            "birth_local": civil.isoformat(), "birth_utc": instant.isoformat(), "source_offset_seconds": r["offset"],
            "sex": r["sex"], "shift_minutes": shift_minutes, "clock_basis": "source_local_civil",
            "solar_term_reference": "same instant expressed in UTC+08:00", "pillars": pillars, "day_master": dm,
            "qiyun": {"direction": "forward" if yun.isForward() else "backward", "sect": 2,
                      "delay_years": yun.getStartYear(), "delay_months": yun.getStartMonth(), "delay_days": yun.getStartDay(), "delay_hours": yun.getStartHour(),
                      "start_utc": start_utc.isoformat(), "algorithm_resolution": "source minute interval mapped to two qiyun hours"},
            "decades": periods, "natal_relations": natal_relations, "natal_group_patterns": group_patterns([x[1] for x in raw.values()]),
            "strength_annotation": {"method": "registered weighted element tally; not canonical strength adjudication", "element_weights": dict(weights), "support_fraction": support,
                                    "research_class": "weak" if support < .45 else "strong" if support > .55 else "balanced"},
            "month_main_ten_god_annotation": main_hidden["ten_god"], "yongshen": None,
            "interpretive_clauses":interpret_pillars(raw),
            "complete_traditional_interpretation": False, "death_probability": None}


def annual_features(chart, year):
    if not isinstance(year, int) or not 1880 <= year <= 2200:
        raise InputError("Unsupported snapshot year")
    birth = datetime.fromisoformat(chart["birth_local"])
    snapshot = datetime(year,7,1,12)
    instant = (snapshot - timedelta(seconds=chart["source_offset_seconds"])).replace(tzinfo=UTC)
    if snapshot < birth:
        return {"year": year, "status": "before_birth", "score": None}
    decade = next((d for d in chart["decades"] if datetime.fromisoformat(d["start_utc"]) <= instant < datetime.fromisoformat(d["end_utc_exclusive"])), None)
    if decade is None:
        return {"year": year, "status": "outside_registered_decadal_interval", "score": None}
    annual = JIAZI[(year-4) % 60]
    natal = {k:v["ganzhi"] for k,v in chart["pillars"].items()}
    relations = [{"scope":scope,"natal_pillar":k,**relation(gz,v)} for scope,gz in [("yearly",annual),("decadal",decade["ganzhi"])] for k,v in natal.items()]
    counts = {k:sum(int(r[k]) for r in relations) for k in relation("甲子","甲子")}
    assert len(relations) == 8 and 0 <= counts["branch_clash"] <= 8
    combo = list(natal.values()) + [annual,decade["ganzhi"]]
    dm = chart["day_master"]
    resources = [g for g in [annual[0],decade["ganzhi"][0]] if (ELEMENTS.index(element(g))+1)%5==ELEMENTS.index(element(dm))]
    return {"year": year, "snapshot_local": snapshot.isoformat(), "status": "computed_for_registered_conventions",
            "score": counts["branch_clash"] / 8.0, "score_name": "branch_clash_rate", "score_is_event_probability": False,
            "yearly_pillar": describe_pillar(annual,dm), "decadal_pillar": describe_pillar(decade["ganzhi"],dm), "decadal_index":decade["index"],
            "comparison_count":8,"relation_counts":counts, "annual_decadal_relation":relation(annual,decade["ganzhi"]),
            "six_pillar_group_patterns":group_patterns([g[1] for g in combo]),
            "resource_context": {"resource_stems_in_year_or_decade":resources,"rescue_adjudicated":False},
            "interpretive_clauses":interpret_pillars(natal,{"yearly":annual,"decadal":decade["ganzhi"]}),
            "death_probability":None}


def build_natal(birth, shift_minutes=0):
    return build_chart(birth, shift_minutes)


def annual_signals(natal, year):
    result = annual_features(natal, int(year))
    return {"primary_score":result.get("score"), "status":result["status"], "components":result}


def evaluate(row, years, shift_minutes=0, include_chart=False, detailed=False):
    try:
        chart = build_chart(row,shift_minutes)
        annual = [annual_features(chart,int(y)) for y in years]
        if not detailed:
            annual = [{k:r[k] for k in ("year","status","score","decadal_index","score_name") if k in r} |
                      {"matched_interpretive_rules":[x["rule"] for x in r.get("interpretive_clauses",{}).get("clause_matches",[]) if x["structural_match"]]} for r in annual]
        result = {"study_id":chart["study_id"],"engine":VERSION,"status":chart["status"],"annual":annual}
        if include_chart:result["chart"] = chart
        return result
    except (InputError,ValueError,TypeError,KeyError) as exc:
        return {"study_id":str(row.get("study_id","")),"engine":VERSION,"status":"abstain","reason":str(exc),"annual":[{"year":int(y),"score":None,"status":"abstain"} for y in years]}
