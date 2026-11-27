# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exploratory whole-record reference refits; no calibrated coverage claim."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
import math
import time
import numpy as np
from threshold_precision import ExactWeights,classify


def score_array(value):
    value = np.asarray(value, float)
    if value.ndim != 3 or value.shape[1:] != (40, 4) or not len(value):
        raise ValueError('Expected nonempty (n,40,4) scores')
    if not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
        raise ValueError('Scores must be finite and bounded')
    return value


@dataclass
class RecordDesign:
    weights: np.ndarray
    groups: list

    @classmethod
    def from_frame(cls, weights, strata, frame_counts):
        weights = np.asarray(weights, float)
        strata = np.asarray(strata, str)
        if weights.ndim != 1 or strata.shape != weights.shape or not len(weights):
            raise ValueError('One stratum and weight per record required')
        if not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError('Finite positive design weights required')
        keys = sorted(set(strata.tolist()))
        counts = {str(k): int(v) for k, v in frame_counts.items()}
        if set(keys) != set(counts):
            raise ValueError('Every eligible stratum must be sampled')
        groups = []
        for key in keys:
            ids = np.flatnonzero(strata == key)
            n, N = len(ids), counts[key]
            if N < n or not np.allclose(weights[ids], N/n, rtol=0, atol=1e-9):
                raise ValueError('Invalid stratum frame or weights')
            if n == 1 and N > 1:
                raise ValueError('Non-census singleton stratum: ' + key)
            groups.append((ids, n, N, math.sqrt(1-n/N)))
        return cls(weights, groups)

    def draw(self, rng):
        result = self.weights.copy()
        for ids, n, N, root_fpc in self.groups:
            if n == N:
                continue
            counts = rng.multinomial(n-1, np.full(n, 1/n))
            factors = 1-root_fpc + root_fpc*n/(n-1)*counts
            result[ids] *= factors
        return result

    def exact_weights(self):
        values=[None]*len(self.weights)
        for ids,n,N,_ in self.groups:
            for i in ids:values[int(i)]=Fraction(N,n)
        return ExactWeights(values)


class ReferenceCache:
    """Cache raw-value indices; recompute reference masses at every draw."""
    def __init__(self, reference, targets):
        self.raw = {'reference': score_array(reference)}
        for name, values in targets.items():
            if name == 'reference':
                raise ValueError('Reserved reference label')
            self.raw[name] = score_array(values)
        self.tables = []
        for band in range(4):
            for system in range(4):
                ref = self.raw['reference'][:, band*10:band*10+10, system].reshape(-1)
                support, inverse = np.unique(ref, return_inverse=True)
                queries = {}
                for name, raw in self.raw.items():
                    values = raw[:, band*10:band*10+10, system]
                    queries[name] = (np.searchsorted(support, values, 'left'),
                                     np.searchsorted(support, values, 'right'))
                self.tables.append((band, system, len(support), inverse, queries))

    def transform(self, reference_weights, *, full=False, exact_design_weights=None):
        weights = np.asarray(reference_weights, float)
        if weights.shape != (len(self.raw['reference']),) or not np.isfinite(weights).all() or np.any(weights < 0) or weights.sum() <= 0:
            raise ValueError('Invalid reference replicate weights')
        repeated = np.repeat(weights, 10)
        oracle=exact_design_weights
        def exact_weights():
            nonlocal oracle
            if oracle is None:oracle=ExactWeights.from_floats(weights)
            return oracle
        if full:
            output = {k:np.empty_like(v) for k,v in self.raw.items()}
        else:
            output = {k:np.zeros(v.shape[:2], dtype=np.uint8) for k,v in self.raw.items()}
        for band, system, size, inverse, queries in self.tables:
            masses = np.bincount(inverse, weights=repeated, minlength=size)
            cumulative = np.r_[0.0, np.cumsum(masses)]
            boundary_cache={}
            for name, (left, right) in queries.items():
                q = (cumulative[left]+cumulative[right])/(2*cumulative[-1])
                if full:
                    output[name][:,band*10:band*10+10,system] = q
                else:
                    output[name][:,band*10:band*10+10] += classify(q,left,right,inverse.reshape(-1,10),exact_weights,cache=boundary_cache)
        if full:
            return output
        return {name:(counts >= 3).mean(axis=1) for name,counts in output.items()}


def run_sensitivity(reference, targets, *, draws, reference_seed, target_seeds):
    """Return empirical sensitivity ranges, not calibrated confidence claims."""
    started = time.monotonic()
    names = sorted(targets)
    if set(names) != set(target_seeds) or draws < 2:
        raise ValueError('Every target requires one prespecified seed and >=2 draws')
    inputs = {'reference':reference, **targets}
    designs = {name:RecordDesign.from_frame(d['weights'],d['strata'],d['frame_counts']) for name,d in inputs.items()}
    rngs = {'reference':np.random.default_rng(reference_seed)}
    rngs.update({name:np.random.default_rng(target_seeds[name]) for name in names})
    cache = ReferenceCache(reference['scores'], {name:d['scores'] for name,d in targets.items()})
    # The unperturbed point and fixed-CDF comparator use exact N_h/n_h. Refit
    # draws instead use the exact binary ratios of their supplied float weights.
    fixed_rates = cache.transform(reference['weights'],exact_design_weights=designs['reference'].exact_weights())
    fixed_reference = float(np.average(fixed_rates['reference'], weights=reference['weights']))
    full = np.empty((draws, len(names)))
    fixed_cdf = np.empty_like(full)
    reference_rates = np.empty(draws)
    for b in range(draws):
        wr = designs['reference'].draw(rngs['reference'])
        rates = cache.transform(wr)
        jr = float(np.average(rates['reference'], weights=wr))
        reference_rates[b] = jr
        jr_fixed = float(np.average(fixed_rates['reference'], weights=wr))
        for k, name in enumerate(names):
            wt = designs[name].draw(rngs[name])
            full[b,k] = np.average(rates[name],weights=wt)-jr
            fixed_cdf[b,k] = np.average(fixed_rates[name],weights=wt)-jr_fixed
    results=[]
    for k,name in enumerate(names):
        point=float(np.average(fixed_rates[name],weights=targets[name]['weights'])-fixed_reference)
        results.append({'slot':name,'point_delta_joint_rate':point,
            'full_reference_refit_percentile_range95':np.quantile(full[:,k],[.025,.975]).tolist(),
            'full_reference_refit_mean':float(full[:,k].mean()),
            'full_reference_refit_variance':float(full[:,k].var(ddof=1)),
            'fixed_CDF_two_sample_percentile_range95':np.quantile(fixed_cdf[:,k],[.025,.975]).tolist(),
            'fixed_CDF_two_sample_variance':float(fixed_cdf[:,k].var(ddof=1))})
    return {'status':'computed_exploratory_sensitivity','draws':draws,
        'reference_seed':reference_seed,'target_seeds':target_seeds,
        'reference_draw_shared_across_targets':True,
        'reference_CDF_refitted_each_draw':True,
        'threshold_precision':'Exact >=4/5 near-boundary oracle; baseline uses rational N_h/n_h, replicate CDFs use exact binary ratios of supplied floating replicate weights',
        'replicate_weight_rule':'g_i=1-sqrt(1-n_h/N_h)+sqrt(1-n_h/N_h)*n_h/(n_h-1)*m_i; m~Multinomial(n_h-1,1/n_h); census unchanged',
        'full_refit_reference_joint_percentile_range95':np.quantile(reference_rates,[.025,.975]).tolist(),
        'targets':results,'runtime_seconds':round(time.monotonic()-started,6),
        'interpretation':'Empirical 2.5th–97.5th percentile sensitivity ranges. No calibrated coverage for the nonsmooth threshold functional, no multiplicity-adjusted conclusion, and no mortality/AI-risk interpretation.',
        'excluded_uncertainty':['source undercoverage','registration delay outside sampled archives','clock/location error','engine or traditional-rule validity','global population generalization']}
