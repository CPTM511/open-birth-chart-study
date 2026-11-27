# Reconstructing the Mexico 2009 model inputs

Two calculations using the official source archives reproduced the entire frozen 2,000-row model-input file, including the order and every serialized byte. Its SHA-256 is `cff3aae86557673296be0ca5fe186b2b1bc1ed696aa0dedce75bfe390ee3935e`. All 52 occurrence-state-by-sex stratum sizes and sample quotas match the prescoring manifest. The model input contains birth variables used by the four chart engines. The scoring coordinator also checks a separate private metadata file. Its original byte sequence remains unverified. [Prescoring manifest](../../mexico/samples/mexico_2000s/sampling_manifest.json) · [Replay receipt](replay_receipt.json)

| Registration archive | Physical records | Born in 2009 | Eligible records |
|---|---:|---:|---:|
| 2009 | 2,577,214 | 1,630,785 | 1,231,004 |
| 2010 | 2,643,908 | 542,132 | 414,431 |
| Combined | 5,221,122 | 2,172,917 | 1,645,435 |

The replay matches the archived municipality code and normalized name to the 2026 INEGI designation and the 2020 census. It uses the coordinates of the designated seat, checks its name when the 2026 source supplies one, requires a valid birth clock, registration date and an unambiguous historical UTC offset, then ranks physical records using the frozen seed. The source ID consists of `INEGI-NACIM`, the four-digit registration archive year, a hyphen and the eight-digit one-based DBF record ordinal. The resulting model-input digest independently verifies the selected records and their birth variables. Seats approximate municipal birth locations, and registrations after 2010 fall outside this cohort. [2009 registration archive](https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2009/natalidad_base_datos_2009_dbf.zip) · [2010 registration archive](https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2010/natalidad_base_datos_2010_dbf.zip) · [2020 census locality coordinates](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip) · [INEGI geographic catalogue](https://www.inegi.org.mx/servicios/catalogounico/)

## Reproduce the verification

Place the two original ZIPs under `/private/inegi/YEAR/natalidad_base_datos_YEAR_dbf.zip`. Save the 32 JSON responses from `https://gaia.inegi.org.mx/wscatgeo/v2/mgem/NN` as `seats-NN.json`, with `NN` running from `01` through `32`. The receipt records the SHA-256 of each catalogue response because the online catalogue can change. Point Python at compiled IANA 2026c time zones. The script writes aggregate evidence to standard output. The optional private output is created only after the full input digest matches. [IANA 2026c source](https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz)

```sh
PYTHONTZPATH=/private/zoneinfo-2026c python rounds/r10/recovery/mexico2009/rebuild_inputs.py \
  --archives /private/inegi \
  --iter /private/iter_00_cpv2020_csv.zip \
  --seats /private/inegi-seats \
  --private-inputs /private/mexico_2000s/birth_inputs.jsonl
```
