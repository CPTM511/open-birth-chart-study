"""Run a synthetic two-category NumPy 2.3.5 portability check. No study data needed."""

import json
import math
import platform
from fractions import Fraction

import numpy as np


def central_proposal(n, p, fm, uniforms):
    """Evaluate the elementary central branch of NumPy's BTPE binomial sampler."""
    m = math.floor(fm)
    q = 1.0 - p
    p1 = math.floor(2.195 * math.sqrt(n * p * q) - 4.6 * q) + 0.5
    center = m + 0.5
    left, right = center - p1, center + p1
    c = 0.134 + 20.5 / (15.3 + m)
    a = (fm - left) / (fm - left * p)
    lambda_left = a * (1.0 + a / 2.0)
    a = (right - fm) / (right * q)
    lambda_right = a * (1.0 + a / 2.0)
    p4 = p1 * (1.0 + 2.0 * c) + c / lambda_left + c / lambda_right
    u, v = uniforms
    if u * p4 > p1:
        raise ValueError("This fixture requires NumPy's central BTPE branch")
    return {
        "initial_value_hex": fm.hex(),
        "integer_center": m,
        "first_category": math.floor(center - p1 * v + u * p4),
    }


def main():
    n = 92
    p = 1 / 3
    seed = 2
    probabilities = [p, 2 / 3]
    uniforms = tuple(map(float, np.random.default_rng(seed).random(2)))
    # Fraction gives the exact product and sum of the binary64 inputs. The
    # final conversion rounds only once, as a fused multiply-add would.
    single_round = float(n * Fraction.from_float(p) + Fraction.from_float(p))
    double_round = n * p + p
    generator = np.random.default_rng(seed)
    before = generator.bit_generator.state
    sample = generator.multinomial(n, probabilities).tolist()
    print(json.dumps({
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "bit_generator": generator.bit_generator.__class__.__name__,
        "seed": seed,
        "n": n,
        "p_hex": [value.hex() for value in probabilities],
        "initial_state": before,
        "first_two_uniforms_hex": [value.hex() for value in uniforms],
        "single_rounding": central_proposal(n, p, single_round, uniforms),
        "separate_rounding": central_proposal(n, p, double_round, uniforms),
        "observed_binomial": int(np.random.default_rng(seed).binomial(n, p)),
        "observed_multinomial": sample,
    }, indent=2))


if __name__ == "__main__":
    main()
