# Reproduce the Shoushi coordinate bridge

Use the pinned Python, Swiss Ephemeris and Astronomy Engine versions from the [project setup](../../docs/REPRODUCING.md). The primary astronomical input comes from the same geocentric solar adapter used by the project. Calendar labels are Gregorian and require an explicit offset for modern input. The archived integer and fractional values come from the same pinned public revision in two distinct delivery formats. The two downloads are a source-integrity check on that edition.

```sh
export PYTHONPATH="$PWD/src"
python -m rounds.r32.input_data acquire --format page --job "$R32_A"
python -m rounds.r32.input_data acquire --format render --job "$R32_B"
python -m rounds.r32.input_data seal --source "$R32_A/yuanshi.html" \
  --replay-source "$R32_B/yuanshi.html" --output "$R32_A/source_numeric.json"
python -m rounds.r32.replay --output "$R32_A/results.json"
python -m unittest discover -s rounds/r32 -v
```

The first extraction identifies the two files by their own byte hashes. Page chrome can change with the rendering software even for a pinned revision. Check the numeric fields against [source_numeric.json](source_numeric.json) if the HTML hashes differ. The replay reads the sealed table in this round's directory. Its source and code hashes identify the analyzed version. The second computation of the angular geometry integrates the traversed lengths exactly with rational numbers. The dynamic modern interval labels are also checked directly in equatorial coordinates.

Run the released adapter on a declared example timestamp and site longitude.

```sh
python -m rounds.r32.coordinates --birth '2000-01-01T00:02:00+08:00' --longitude 100
```

The example assigns 子 to the specified civil time and 亥 to the prior day's local mean solar time. Both readings share the same UTC astronomical instant. The command reports solar palace and lodge, transferred degree, and nominal first change of childhood period where the registered geometry supports it. There are separate values for the two palace boundaries, the printed versus reprojected coordinate methods, the head and tail transfers, and both time conventions. A shifted palace can be too narrow to contain the transferred degree. The report gives that status and leaves the age uncomputed.

Data references are [the pinned History of Yuan](https://zh.wikisource.org/wiki/Special:PermanentLink/1959444), the previously transcribed [R22 boundaries](../r22/sources.json), and the two late-Ming readings under [the registration](REGISTRATION.zh.md). The [source receipt](source_numeric.json) records only the derived numerical tables and metadata needed for this comparison.
