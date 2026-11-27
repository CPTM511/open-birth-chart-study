# R10 — Expanding observed birth cohorts into the 2020s

This is the dated pre-scoring protocol freeze for R10. R8 and R9 are preserved.
No new R10 real chart scores have been calculated or inspected at this freeze;
source catalogues, schemas and birth-field quality audits have been inspected.

[Frozen protocol](protocol.json) defines seven source-year slots, 2,000 records
per eligible slot, a fixed R8 Brazil2006 reference, unchanged scoring rules with
an explicit additive birth-date-domain extension, and complete ages20–59.
The new 2020s inputs are actual recorded births, never simulated future people.

Brazil2005 lacks a birth clock; its single2007 fallback is used. Brazil2010,
2020 and2024 add earlier2010s and two2020s observation years. Mexico2005 lacks
a clock; its single2009 fallback can qualify only if its municipality fields
can be joined to documented official municipal-seat references. Mexico2020
combines registration2020 and2021 to reduce same-year registration truncation.
These are restricted source frames, not complete decade or global samples.

Primary intervals use9,999 whole-record resamples and retain all seven planned
slots for multiplicity. A separate999-draw reference-refitting sensitivity
addresses instability in the selected empirical reference, without claiming
exact inferential coverage. The statistical and date-scope implementation
must pass synthetic checks before real scoring. All exclusions are reported.

The five additional country leads did not establish an accessible full-input
frame. Aggregate global population benchmarks are kept separate from individual
birth inputs. Death-outcome validation remains paused. No result in this round
is an AI-replacement, disaster or civilizational-collapse probability.

This original README and protocol will remain as the public freeze record.
Completed results will be added in separate dated reports.
