"""Independent small-array/enumeration checks for the R9 estimator arithmetic."""
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import numpy as np

from fixed_reference import FixedReference, WeightedMidCDF, conditional_frame_interval, rescaled_stratum_bootstrap


def run_checks():
    checks = []
    x = np.array([0, 0.25, 0.25, 0.75, 1.0])
    w = np.array([1, 3, 2, 4, 1])
    cdf = WeightedMidCDF.fit(x, w)
    queries = [-0.1, 0, 0.125, 0.25, 0.5, 0.75, 1, 1.1]
    for query in queries:
        exact = sum(Fraction(int(weight)) * (int(value < query) + Fraction(int(value == query), 2)) for value, weight in zip(x, w)) / sum(map(int, w))
        assert abs(float(cdf(query)) - float(exact)) < 1e-14
    checks.append("weighted mid-CDF matches Fraction direct enumeration at ties, gaps and exterior queries")
    assert abs(np.average(cdf(x), weights=w) - 0.5) < 1e-14
    checks.append("weighted reference mid-CDF mean equals one half")

    raw = np.fromfunction(lambda i, a, s: ((i + a + s) % 5) / 4, (3, 40, 4))
    ref = FixedReference(raw, [1, 2, 5])
    result = ref.summarize(raw, [1, 2, 5])
    assert abs(result["delta_joint_rate"]) < 1e-14
    assert abs(result["delta_L"]) < 1e-14
    checks.append("four-system self-reference identity including unequal weights")
    constant = FixedReference(np.full((2, 40, 4), 0.4), [1, 3])
    assert constant.joint_rate == 0 and np.all(constant.transform(np.full((2,40,4), 0.4)) == 0.5)
    checks.append("constant profiles are tied at 0.5 and never elevated")

    ordered = list(product(range(3), repeat=3))
    v = [Fraction(0), Fraction(1, 4), Fraction(3, 4)]
    center = sum(v) / 3
    exact_means = [sum(v[i] for i in draw) / 3 for draw in ordered]
    empirical_variance = sum((m - center) ** 2 for m in exact_means) / len(ordered)
    correction_squared = (1 - Fraction(3, 12)) * Fraction(3, 2)
    corrected_variance = empirical_variance * correction_squared
    sample_variance = sum((z - center) ** 2 for z in v) / 2
    expected_variance = (1 - Fraction(3, 12)) * sample_variance / 3
    assert corrected_variance == expected_variance

    class EnumeratedRng:
        def multinomial(self, n, probabilities, size):
            assert n == 3 and size == 27 and np.allclose(probabilities, [1/3]*3)
            return np.array([[draw.count(j) for j in range(3)] for draw in ordered])

    actual, analytic = rescaled_stratum_bootstrap(np.array(list(map(float,v))), 12, 27, EnumeratedRng())
    direct = float(center) + np.sqrt(float(correction_squared)) * (np.array(list(map(float,exact_means))) - float(center))
    assert np.max(np.abs(actual - direct)) < 1e-14
    assert abs(actual.var(ddof=0) - float(expected_variance)) < 1e-14
    assert abs(analytic - float(expected_variance)) < 1e-14
    checks.append("all 27 ordered whole-record bootstraps match compressed multinomial arithmetic and exact finite-population variance")

    census = conditional_frame_interval([0.1, 0.7], ["A", "B"], {"A":1, "B":1}, seed=1)
    assert census["analytic_design_variance"] == 0 and np.allclose(census["interval95"], [0.4,0.4])
    missing = conditional_frame_interval([0.1,0.7], ["A","B"], {"A":3,"B":1}, seed=1)
    assert missing["status"] == "unavailable"
    checks.append("census variance is zero; non-census singleton variance is unavailable")

    values = np.linspace(0.2, 0.7, 40)
    shifted = values + 0.1
    def direct_midranks(a):
        return np.array([(sum(a < z) + 0.5*sum(a == z))/len(a) for z in a])
    assert np.array_equal(direct_midranks(values), direct_midranks(shifted))
    frozen = WeightedMidCDF.fit(values, np.ones(40))
    assert frozen(shifted).mean() > frozen(values).mean()
    checks.append("within-record ranks miss a monotone level shift while fixed-reference levels detect it")

    p, n, years = Fraction(3,10), 2000, 40
    correct = p*(1-p)/n
    incorrect = p*(1-p)/(n*years)
    assert correct/incorrect == 40
    checks.append("record-year pseudo-independence understates variance by exactly 40 for repeated Bernoulli record outcomes")
    return {"status":"passed", "checks":checks, "count":len(checks), "independent_arithmetic":"Fractions and complete ordered-bootstrap enumeration; no real R9 scores inspected"}


if __name__ == "__main__":
    result = run_checks()
    out = Path(__file__).with_name("math_verification.json")
    out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))
