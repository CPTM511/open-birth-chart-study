# R43 reproduction

Use Python 3.12 with the pinned `requirements.txt`. Info-ZIP `unzip` needs
Deflate64 and ZIP64 streaming support for the U.S. file. Keep both downloaded
copies in a private directory. Only national hour-by-minute counts are
released. The independently checked R41 grid and results must be present in
the checkout before running a target comparison.

From the repository root:

```sh
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src:$PWD"

umask 077
r43_job=$(mktemp -d)
mkdir "$r43_job/source-a" "$r43_job/source-b"
brazil='https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINASC/csv/DNBR2006_csv.zip'
us='https://ftp.cdc.gov/pub/health_Statistics/nchs/Datasets/DVS/natality/Nat2016us.zip'
for copy in source-a source-b; do
  curl --fail --location "$brazil" -o "$r43_job/$copy/brazil2006.zip"
  curl --fail --location "$us" -o "$r43_job/$copy/us2016.zip"
done
python -m rounds.r43.donors \
  --first "$r43_job/source-a" --second "$r43_job/source-b" \
  --output "$r43_job/donor_counts.json"
cmp "$r43_job/donor_counts.json" rounds/r43/donor_counts.json

git merge-base --is-ancestor 1d7f0a3879e680fa82d3ebffb995b01082eb362b HEAD
python -m rounds.r43.check_release
python -m unittest rounds.r43.test_transport
python -m rounds.r43.analyze --donors "$r43_job/donor_counts.json" \
  --certificates "$r43_job/certificates.json.gz" --results "$r43_job/results.json"
python -m rounds.r43.check_release --donors "$r43_job/donor_counts.json" \
  --certificates "$r43_job/certificates.json.gz" --results "$r43_job/results.json"
```

The archive receipt lists byte counts, checksums, exclusions, and matching
clock counts from both parsing routes. The checked two-dimensional counts are
indexed by civil hour 0–23 and then minute 0–59. Brazil uses dates and clock
codes from SINASC. The NCHS file covers births occurring in the 50 states and
District of Columbia, including births to people resident abroad. Its year
and clock are at positions 9–12 and 19–22 inclusive.
[NCHS layout and record counts](https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Dataset_Documentation/DVS/natality/UserGuide2016.pdf)

Each sparse certificate entry gives the zero-based position in `date_order`,
the minute, and the assigned mass multiplied by that donor's hour total.
Rows and columns of this allocation must recover the exact prescribed
margins. The cost is the total high-mark count across the two R41 parameter
values and 40 ages. The upper endpoint uses negative costs in the minimizer.
Integer potentials provide an equal dual objective. A replay on another
solver build may choose a different optimal allocation. The exact bounds
and all registered point and threshold results must agree.
