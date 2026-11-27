# Reconstructing the Mexico 2020 model inputs

Two implementations selected the same 2,000 records from the 2020 and 2021 registration archives and reproduced every byte of the model input frozen before target scoring. Both matched the population and sample counts in all 54 occurrence-state-by-sex strata. For every selected record, a second comparison matched its archive and physical row, occurrence locality, registration date and delay, study ID, selection rank, stratum and design fraction. The sum of the exact sampling weights was 1,369,906. [Prescoring manifest](../../mexico/samples/mexico2020/sampling_manifest.json) · [Aggregate replay receipt](replay_receipt.json)

| Registration archive | Physical records | Births recorded as occurring in 2020 | Eligible records |
|---|---:|---:|---:|
| 2020 | 1,629,211 | 1,169,571 | 952,075 |
| 2021 | 1,912,178 | 504,677 | 417,831 |
| Combined | 3,541,389 | 1,674,248 | 1,369,906 |

Each archive supplies its own locality catalogue. The recovery matched its locality code and normalized name against the nationwide 2020 census. It required a valid clock and explicit sex, a valid registration chronology, resolved geography and a single historical UTC offset. The recovered sample contains records from 27 states. Registrations after 2021 fall outside the frame, and the locality point approximates the place of birth. [2020 registration archive](https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2020/natalidad_base_datos_2020_dbf.zip) · [2021 registration archive](https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/2021/natalidad_base_datos_2021_dbf.zip) · [National 2020 census](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip)

The script prints an aggregate receipt. Optional private outputs are the verified model input and a newly serialized record of the selection facts. The original round also sealed a historical metadata file with SHA-256 `3b3dba53b805e3abdee24764d16f704bd2247a96ce4f86596fad5761be768851`. This replay verifies the model input, selection and weight facts. Recovery of the original full metadata bytes is a separate check.

```sh
PYTHONTZPATH=/private/zoneinfo-2026c python rounds/r10/recovery/mexico2020/rebuild_inputs.py \
  --archives /private/inegi \
  --iter /private/iter_00_cpv2020_csv.zip \
  --private-inputs /private/mexico2020/birth_inputs.jsonl \
  --private-design /private/mexico2020/reconstructed_design.jsonl
```

Store the publisher's original ZIP under `YEAR/natalidad_base_datos_YEAR_dbf.zip` in the private archive directory. Individual records and design rows stay in private storage.
