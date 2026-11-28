"""Propose integer extremizers for the hour-specific transportation problem."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from rounds.r27.archive_source import require


def extremizers(date_counts, minute_counts, hits):
    day_count, minute_count = len(date_counts), len(minute_counts)
    size = day_count * minute_count
    donor_total, target_total = sum(minute_counts), sum(date_counts)
    rows = [count * donor_total for count in date_counts]
    columns = [count * target_total for count in minute_counts]
    require(donor_total > 0 and len(hits) == day_count and all(len(row) == minute_count for row in hits),
            "Incompatible transportation margins or score grid")
    variables = np.arange(size)
    row_index, column_index = variables // minute_count, variables % minute_count
    nonfinal = column_index < minute_count - 1
    # The final column constraint follows from the others and the row sums.
    constraints = coo_matrix(
        (np.ones(size + int(nonfinal.sum())),
         (np.concatenate((row_index, day_count + column_index[nonfinal])),
          np.concatenate((variables, variables[nonfinal])))),
        shape=(day_count + minute_count - 1, size),
    ).tocsc()
    costs = np.asarray(hits, dtype=np.int64).reshape(size)
    solutions = {}
    for label, sense in (("minimum", 1), ("maximum", -1)):
        result = linprog(sense * costs, A_eq=constraints, b_eq=rows + columns[:-1], method="highs-ds")
        require(result.success, f"Transportation solve failed for {label}: {result.message}")
        allocations = np.rint(result.x).astype(np.int64)
        potentials = np.rint(result.eqlin.marginals).astype(np.int64).tolist()
        support = [
            [int(row_index[index]), int(column_index[index]), int(allocations[index])]
            for index in np.flatnonzero(allocations)
        ]
        solutions[label] = {
            "allocation": support,
            "row_potentials": potentials[:day_count],
            "column_potentials": potentials[day_count:] + [0],
            "signed_objective": sum(sense * hits[day][minute] * weight for day, minute, weight in support),
        }
    return solutions
