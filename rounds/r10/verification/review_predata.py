"""Independent pre-target review of domain extension and replicate arithmetic.

Uses only source code, declared protocol, and explicit synthetic fixtures.
Does not open R10 source samples, target profiles, target effects, or outcomes.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timedelta
import difflib
from fractions import Fraction
import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
METHODS = ROOT / "rounds/r10/methods"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(METHODS))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def source_diff_checks():
    manifest = json.loads((METHODS / "date_scope_diff.json").read_text())
    results = []
    for item in manifest["files"]:
        a, b = [ROOT / item[k] for k in ["source", "additive_copy"]]
        assert digest(a) == item["source_sha256"] and digest(b) == item["copy_sha256"]
        before, after = a.read_text(), b.read_text()
        actual = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=item["source"], tofile=item["additive_copy"]))
        assert actual == item["unified_diff"]
        expected = before
        if a.name in ["astronomy.py", "bazi_engine.py"]:
            expected = expected.replace("1880 <= civil.year <= 2019", "1880 <= civil.year <= 2025").replace("1880–2019", "1880–2025")
        elif a.name == "ziwei_bridge.cjs":
            expected = expected.replace("y>2019", "y>2025")
        elif a.name == "io.py":
            expected = expected.replace("1880<=civil.year<=2019", "1880<=civil.year<=2025")
        elif a.name == "run_profiles.py":
            expected = expected.replace("ROOT=Path(__file__).resolve().parents[1]", "ROOT=Path(__file__).resolve().parents[3]")
            expected = expected.replace("from open_birth_chart.io import load_source,sha256,chart_key", "from r10_io import load_source,sha256,chart_key")
            expected = expected.replace("from open_birth_chart import bazi_engine as bz,ziwei_engine as zw,qizheng_engine as qz,western_engine as west", "from open_birth_chart_r10 import bazi_engine as bz,ziwei_engine as zw,qizheng_engine as qz,western_engine as west")
            old_tree, new_tree = ast.parse(before), ast.parse(after)
            for name in ["score_record", "init_worker"]:
                old_fn = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                new_fn = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                x = ast.dump(old_fn, include_attributes=False)
                y = ast.dump(new_fn, include_attributes=False).replace("module='open_birth_chart_r10'", "module='open_birth_chart'")
                assert x == y, "Executable scoring function changed: " + name
            # Runner's only remaining statement difference must be the run-seal
            # metadata assignment in main, not task creation or score execution.
            x = ast.parse(expected)
            y = ast.parse(after)
            xm = next(n for n in x.body if isinstance(n, ast.FunctionDef) and n.name == "main")
            ym = next(n for n in y.body if isinstance(n, ast.FunctionDef) and n.name == "main")
            def run_assignment(node):
                return isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "run" for t in node.targets)
            assert sum(run_assignment(n) for n in xm.body) == sum(run_assignment(n) for n in ym.body) == 1
            xm.body = [n for n in xm.body if not run_assignment(n)]
            ym.body = [n for n in ym.body if not run_assignment(n)]
            assert ast.dump(x, include_attributes=False) == ast.dump(y, include_attributes=False)
            results.append({"file": item["source"], "hash_and_full_diff_match": True, "scoring_AST_unchanged": True, "remaining_change": "run provenance metadata only"})
            continue
        assert expected == after, "Undeclared executable change: " + a.name
        results.append({"file": item["source"], "hash_and_full_diff_match": True, "only_authorized_domain_change": True})
    protocol = json.loads((ROOT / "rounds/r10/protocol.json").read_text())
    for path, expected in protocol["score_rules"]["original_engine_hashes"].items():
        assert digest(ROOT/path) == expected, "Original frozen engine changed: " + path
    return results


def engine_fixtures():
    old = module("independent_old_runner", ROOT/"scripts/run_profiles.py")
    new = module("independent_new_runner", METHODS/"run_profiles.py")
    old.init_worker()
    new.init_worker()
    def fixture(label, sex="M", offset=0, latitude=0., longitude=0.):
        civil = datetime.fromisoformat(label)
        first = civil.year+20+int((civil.month, civil.day) > (7, 1))
        row = {"study_id": "synthetic-independent-review", "source": "SYNTHETIC-ONLY", "birth_local": label,
            "birth_utc": (civil-timedelta(seconds=offset)).isoformat()+"Z", "source_offset_seconds": offset,
            "sex": sex, "calendar": "gregorian", "latitude": latitude, "longitude": longitude,
            "calendar_years": list(range(first, first+40)), "chart_input_key": "synthetic-not-a-person"}
        return row
    legacy, extension = [], []
    try:
        for year in [1880, 2006, 2019]:
            row = fixture(f"{year}-06-01T12:00:00")
            a, b = [runner.score_record((row, "base", 0, None)) for runner in [old, new]]
            assert a["status"] == b["status"] == "computed" and a == b
            legacy.append({"synthetic_birth_year": year, "whole_profile_exact_match": True, "system_age_scores": 160})
        fixtures = [
            fixture("2024-02-29T12:00:00", "F", -10800, -23.55, -46.63),
            fixture("2024-12-31T23:59:00", "M", 28800, 25., 121.),
            fixture("2025-07-02T00:05:00", "F", 0, 0., 0.),
        ]
        for row in fixtures:
            p = new.score_record((row, "base", 0, None))
            assert p["status"] == "computed", p.get("reason")
            values = np.asarray(p["primary_scores"])
            assert values.shape == (40,4) and np.isfinite(values).all() and np.all((values >= 0) & (values <= 1))
            assert p["calendar_years"] == row["calendar_years"]
            extension.append({"synthetic_birth_date": row["birth_local"][:10], "sex": row["sex"],
                "recorded_offset_seconds": row["source_offset_seconds"], "status": p["status"],
                "age_points": 40, "systems": 4, "calendar_first": p["calendar_years"][0], "calendar_last": p["calendar_years"][-1]})
        for label in ["1879-06-01T12:00:00", "2026-06-01T12:00:00"]:
            assert new.score_record((fixture(label), "base", 0, None))["status"] == "abstain"
    finally:
        old.zw_engine.close()
        new.zw_engine.close()
    return {"legacy": legacy, "extension": extension, "out_of_range_1879_and_2026_rejected": True}


def replicate_arithmetic():
    from reference_sensitivity import RecordDesign
    results = []
    for n, N, values in [
        (2, 7, [Fraction(0), Fraction(3,4)]),
        (3, 12, [Fraction(0), Fraction(1,4), Fraction(3,4)]),
        (4, 17, [Fraction(0), Fraction(1,8), Fraction(1,2), Fraction(1)]),
        (5, 8, [Fraction(0), Fraction(0), Fraction(1,2), Fraction(1), Fraction(1)]),
    ]:
        center = sum(values)/n
        deviations = []
        observed = []
        max_error, min_weight = 0., float("inf")
        design = RecordDesign.from_frame([N/n]*n, ["A"]*n, {"A": N})
        for indices in product(range(n), repeat=n-1):
            counts = np.bincount(indices, minlength=n)
            class Counts:
                def multinomial(self, size, probabilities):
                    assert size == n-1 and np.allclose(probabilities, 1/n)
                    return counts
            weights = design.draw(Counts())
            bootstrap_mean = sum(values[i] for i in indices)/(n-1)
            deviations.append(bootstrap_mean-center)
            mean = float(np.average([float(x) for x in values], weights=weights))
            expected = float(center)+math.sqrt(1-n/N)*float(bootstrap_mean-center)
            max_error = max(max_error, abs(mean-expected), abs(weights.sum()-N))
            min_weight = min(min_weight, float(weights.min()))
            observed.append(mean)
        expected_variance = Fraction(N-n,N)*sum((x-center)**2 for x in values)/(n-1)/n
        enumerated_variance = Fraction(N-n,N)*sum(x*x for x in deviations)/len(deviations)
        assert sum(deviations) == 0 and expected_variance == enumerated_variance
        assert abs(float(np.var(observed))-float(expected_variance)) < 1e-14
        assert max_error < 1e-12 and min_weight >= 0
        results.append({"n": n, "N": N, "enumerated_resamples": n**(n-1),
            "exact_variance": str(expected_variance), "max_weight_total_or_mean_error": max_error,
            "minimum_replicate_weight": min_weight})
    return {"enumerations": results, "conclusion": "Exact conditional mean and design-variance identity verified for the linear weighted mean. This does not calibrate the nonlinear refitted threshold interval; the declared exploratory label remains appropriate."}


def independent_threshold_oracle():
    verifier = module("independent_r10_verifier_selftest", HERE/"verify_aggregates.py")
    from precision_reference import PrecisionReference
    from reference_sensitivity import ReferenceCache
    from threshold_precision import ExactWeights
    raw = np.zeros((5,40,4)); raw[3:] = 1
    M = 10**11
    cases = [("exact_boundary", [Fraction(7,5)]*5, Fraction(4,5), True),
        ("strictly_below", [Fraction(M)]*4+[Fraction(M+1)], 1-Fraction(2*M+1,2*(5*M+1)), False),
        ("strictly_above", [Fraction(M+1)]+[Fraction(M)]*4, 1-Fraction(2*M,2*(5*M+1)), True)]
    results = []
    for name, weights, expected, eligible in cases:
        rows = [{"weight": w} for w in weights]
        cdf = verifier.RawSortedReference(rows, raw)
        assert cdf.exact_value(0,0,1.) == expected
        q, flags, diagnostics = cdf.apply(raw)
        assert bool(flags[-1,0,0]) == eligible
        assert np.all(flags[-2:] == eligible)
        floating_weights = np.array([float(w) for w in weights])
        corrected = PrecisionReference(raw, floating_weights, weights)
        assert np.array_equal(corrected.flags(raw), flags)
        actual_rate = float(np.average((flags.sum(axis=2)>=3).mean(axis=1),weights=floating_weights))
        assert abs(corrected.joint_rate-actual_rate) < 1e-15
        assert abs(corrected.summarize(raw,floating_weights)['joint_rate']-actual_rate) < 1e-15
        cache = ReferenceCache(raw, {'same':raw})
        rate = cache.transform(floating_weights,exact_design_weights=ExactWeights(weights))
        assert np.array_equal(rate['reference'],(flags.sum(axis=2)>=3).mean(axis=1))
        assert np.array_equal(rate['same'],rate['reference'])
        if name == 'exact_boundary':
            assert corrected.base.joint_rate == 0 and abs(corrected.joint_rate-.4) < 1e-15
        results.append({"case": name, "exact_q_at_one": str(expected), "exact_ge_four_fifths": eligible,
            "independent_flags_pass": True, "primary_and_refit_baseline_match_independent_oracle":True,
            "corrected_joint_rate":actual_rate,"rational_queries": diagnostics["near_threshold_exact_rational_queries"]})
    # Exercise tie/gap support and zero-mass reference records; the oracle sorts
    # raw observations and uses direct Fractions, not production support indices.
    raw_distinct = np.repeat(np.arange(5)[:,None,None]/4,40*4,axis=1).reshape(5,40,4)
    query_values = np.array([0.,.125,.25,.5,.875,1.])
    query = np.repeat(query_values[:,None,None],40*4,axis=1).reshape(6,40,4)
    for weights in [[0.,3.,0.,2.,0.],[1.4,2.1,.7,3.3,4.1]]:
        exact = [Fraction(*float(w).as_integer_ratio()) for w in weights]
        cdf = verifier.RawSortedReference([{'weight':w} for w in exact],raw_distinct)
        _,flags,_ = cdf.apply(query)
        cached = ReferenceCache(raw_distinct,{'query':query}).transform(weights)['query']
        assert np.array_equal(cached,(flags.sum(axis=2)>=3).mean(axis=1))
    results.append({'case':'refit_binary_weights_with_ties_gaps_and_zero_masses','independent_flags_pass':True})
    # Hand-computed finite-frame joint statistic and variance, not an implementation mirror.
    rows = [{"stratum": "A", "weight": Fraction(4)} for _ in range(3)]
    point, variance, unavailable = verifier.exact_joint_and_variance(np.array([0,10,30]), rows, {"A": (12,3)})
    assert point == float(Fraction(1,3)) and abs(variance-float(Fraction(7,192))) < 1e-16 and not unavailable
    from fixed_reference import conditional_frame_interval
    rows += [{'stratum':'B','weight':Fraction(7,2)} for _ in range(2)]
    joint_counts = np.array([0,10,30,3,37])
    frame = {'A':(12,3),'B':(7,2)}
    point,variance,unavailable = verifier.exact_joint_and_variance(joint_counts,rows,frame)
    primary = conditional_frame_interval(joint_counts/40,np.array(['A']*3+['B']*2),{'A':12,'B':7},seed=202611270313,draws=9999,family_size=7)
    replay = verifier.bootstrap_replay(joint_counts,rows,frame,seed=202611270313,draws=9999,family=7)
    assert abs(point-float(Fraction(15,38))) < 1e-15
    assert abs(primary['analytic_design_variance']-variance)<1e-15
    for key,value in replay.items():assert np.max(np.abs(np.asarray(value)-primary[key]))<1e-13
    results.append({'case':'independent_primary_bootstrap_replay_two_unequal_strata','draws':9999,'family':7,'point_fraction':'15/38','all_interval_endpoints_and_variances_match':True})
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--skip-engine-runtime", action="store_true", help="Only for environments without the pinned engine dependencies; report not run explicitly")
    args = p.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError("Preserve the original review; use another output path")
    result = {"status": "passed", "real_R10_targets_inspected": False, "scope": "Independent pre-target code/domain and arithmetic review; internal second-agent check, not external validation",
        "source_diffs": source_diff_checks(), "engine_fixtures": {"status": "not_run"} if args.skip_engine_runtime else engine_fixtures(),
        "reference_replicate_math": replicate_arithmetic(), "independent_threshold_oracle": independent_threshold_oracle(),
        "reviewed_code_sha256": {str(f.relative_to(ROOT)): digest(f) for f in sorted(METHODS.glob('*.py'))},
        "reviewer_code_sha256": digest(__file__), "verifier_code_sha256": digest(HERE/"verify_aggregates.py")}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"status": result["status"], "real_R10_targets_inspected": False, "output": str(out)}))


if __name__ == "__main__":
    main()
