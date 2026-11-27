# Reproducing the paired clock comparison

Run from the checkout root with the [pinned Python and Node dependencies](../../docs/REPRODUCING.md). Use the [historical Linux x86-64 numeric environment](../r10/recovery/reference/README.md) that reproduced the frozen Brazil 2006 scores. The initial macOS arm64 check exceeds the registered score-agreement limit and changes two Western threshold decisions. [Original-time diagnostic](macos_anchor_check.json)

Retrieve the two copies of the JSE source into separate access-restricted directories. The scorer reads the clock, the recorded sex, and the duplicate minutes-since-midnight column. It discards birth weight. The public [source definition](sources.json) provides the download hash and civil-time inputs. Do not add the published raw file or individual scores to the checkout.

The `R10_JOB` directory is the preserved private replay with `reference/brazil2006/` and `reference/full-frozen-r8-baseline_profiles.jsonl`. Its files are verified against the [R10 registration](../r10/independent_replay/registration.json). For recovery use the [R8 baseline instructions](../../docs/REPRODUCING.md) and [R10 reference check](../r10/recovery/README.md).

Set `R29_JOB` and `R29_RECHECK` to two new directories outside the checkout. Set `JSE_ONE` and `JSE_TWO` to new paths for the two independent downloads, with their parent directories access-restricted.

```sh
umask 077
export OBS_NODE_MODULES="$PWD/node_modules"
curl -fsSL 'https://jse.amstat.org/datasets/babyboom.dat.txt' -o "$JSE_ONE"
curl -fsSL 'https://jse.amstat.org/datasets/babyboom.dat.txt' -o "$JSE_TWO"
cmp "$JSE_ONE" "$JSE_TWO"
python -m rounds.r29.clock_pairs --job "$R29_JOB" --r10-job "$R10_JOB" --jse-data "$JSE_ONE" --jobs 3
python -m rounds.r29.clock_pairs --job "$R29_RECHECK" --r10-job "$R10_JOB" --jse-data "$JSE_TWO" --jobs 3
python -m rounds.r29.compare --job "$R29_JOB" --replay-job "$R29_RECHECK" --r10-job "$R10_JOB" \
  --jse-data "$JSE_ONE" --second-jse-data "$JSE_TWO" --output "$R29_JOB/results.json"
```

For a time at minute 30, the paired branch advances to the following hour. Midnight can change the local date. The UTC shift is equal to the civil shift so the source offset remains fixed. Modeled years stay those assigned to the original birth date by the R10 July 1 convention. A source time already at an hour contributes its unchanged trajectory once to the scoring files and to both variants in analysis.

The comparison checks that both scores are present for every aligned input and that both fresh files match. It compares the recomputed Brazil original-clock scores against the frozen reference and verifies each annual four-system high-score classification by a second exact integer-rank calculation. It then checks all weighted measures as fractions using the original design counts. A changed joint year contributes to exactly one of lost or gained, and contributes to the reversal total even if the net effect cancels.

## Runtime check

The preregistered Brazil comparison is a gate before estimating either cohort's effect. A pair of macOS runs agreed with each other but failed this gate on the frozen Brazil original-clock input. Across 320,000 primary scores, the only nonzero maximum absolute difference was Western astrology at 1.62 × 10⁻¹¹, above 10⁻¹². Two individual Western high-score decisions differed. The four-model joint decision was identical in all 80,000 baseline record-years. The primary computation uses the original Linux x86-64 numerical environment and the registered gate. [macOS anchor diagnostic](macos_anchor_check.json) · [R10 runtime identity](../r10/recovery/reference/replay_receipt.json)

As a separate check prompted by that finding, all R27 Amsterdam trajectories were rescored with the same archive extraction on Linux. The primary and two clock-sensitivity point estimates matched. The largest primary-interval endpoint shift was 1.11 × 10⁻¹⁶ percentage points, and none of the four-system threshold classifications changed. [R27 cross-platform comparison](r27_platform_recheck.json)
