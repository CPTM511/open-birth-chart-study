# R9 — Fixed-reference cohort comparisons and reproducibility

R9 is an additive research iteration. The 130-file R8 source release, scoring
engines, protocols, and results are preserved unchanged. This directory contains
the new protocol and will accumulate clearly dated execution and audit records.

## Protocol freeze

- [Machine-readable protocol](protocol.json)
- [Statistical supplement](methods/PROTOCOL_SUPPLEMENT.md)
- Frozen reference: R8 Brazil 2006, 2,000 source records.
- Intended new frames: Mexico births in 2015, Brazil births in 2016, and an
  earlier Brazil slot. The last slot is unavailable because the official 1996
  and single permitted 2001 fallback archives omit birth time.
- Fixed maximum: 2,000 records per eligible new source-year, with no score-driven
  resizing or replacement of an unavailable source slot.
- New quantities use a fixed reference distribution, not each target person's
  own forty-year ranking. Effects remain structural, not calibrated risk.

At this first public freeze, only source/schema/birth-field quality audits have
been inspected. No new cohort chart scores have been calculated. Before scoring,
synthetic controls and arithmetic checks must be completed and the selected
birth-input hashes sealed. Subsequent work must retain this original statement
as a dated description of the freeze, not imply that completed results existed.

Independent mortality validation remains paused. A separate real-world AI
evidence track does not combine astrological scores with AI risk probabilities.
Neither track estimates global human extinction or replacement probabilities.
