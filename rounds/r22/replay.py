"""Replay the registered Ming-degree and period evidence across all source paths."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from degrees import BRANCHES, DURATIONS, F, GRID, PRINTED_RATES, SOURCE, ShoushiScale
from degrees import age_for_column, column_for, grid_transfer, grid_value, ming_palace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def verify_record(path, expected):
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Unexpected SHA-256 for {path.name}")


def age_record(palace, mansion, degree, expected_age, frames):
    column = column_for(palace, mansion, degree)
    age = age_for_column(column) if column else None
    return {"printed_ming": [palace,mansion,degree], "printed_age": expected_age,
            "grid_column": column, "grid_age": age, "grid_matches": age == expected_age,
            "continuous": {key:scale.project_bin(palace,mansion,degree,palace,"head")
                           for key,scale in frames.items()}}


def project(frames, palace, mansion, degree, ming):
    return {key: {anchor:scale.project_bin(palace,mansion,degree,ming,anchor)
                  for anchor in ("head","tail")}
            for key,scale in frames.items()}


def main(args):
    verify_record(HERE/"protocol.json",args.registration_sha256)
    verify_record(HERE/"sources.json",args.transcription_sha256)
    spec = json.loads((HERE/"protocol.json").read_bytes())
    for name, expected in spec["files_sha256"].items():
        verify_record(ROOT/name,expected)
    originals = SOURCE["numbered_chapter_notes"]
    frames = {k:ShoushiScale(k) for k in ("wikisource_san","shidian_er")}
    transfers = []
    for solar,mansion,degree,hour,ming,wanted_m,wanted_d in originals["gujin_transfers"]:
        grid = grid_transfer(solar,mansion,degree,hour)
        assert grid["ming_palace"] == ming
        received = grid["ming_mansion"], grid["ming_whole_degree"]
        adjacent = grid_value(ming,grid["solar_column"]+1)
        transfers.append({"input":[solar,mansion,degree,hour],"printed":[ming,wanted_m,wanted_d],
                          "grid":grid,"grid_matches":received == (wanted_m,wanted_d),
                          "adjacent_grid":[ming,*adjacent],
                          "continuous":project(frames,solar,mansion,degree,ming)})
    limits = [age_record(*row,frames) for row in originals["gujin_limits"]]
    zi_extended = [age_record("子","女",degree,age,frames)
                   for degree,age in originals["xingxue_zi_limits"]]
    wing = originals["xingxue_solar_wing_example"]
    expected = wing["printed_entries"]
    derived_ming = wing["inferred_ming_palace"]
    implied_hour_for_grid_lookup = BRANCHES[(BRANCHES.index(wing["solar"][0])+3-
                                             BRANCHES.index(derived_ming))%12]
    wing_grid = grid_transfer(*wing["solar"],implied_hour_for_grid_lookup)
    entries = []
    age = F(expected[0][1])
    for i,(palace,printed_age) in enumerate(expected):
        palace_start = BRANCHES[(BRANCHES.index(derived_ming)+i+1)%12]
        assert palace_start == palace
        entries.append({"palace":palace,"printed_age":printed_age,
                        "nominal_age_using_printed_first_age_and_gujin_durations":str(age),
                        "disagreement_years":str(age-printed_age)})
        age += list(DURATIONS.values())[i]
    rates = []
    for name,duration in DURATIONS.items():
        literal = PRINTED_RATES[name]
        day_hint = SOURCE["printed_rates"][name]["days_per_unit"]
        rates.append({"period":name,"years":str(duration),"annual_rate_printed":str(literal),
                      "annual_rate_for_30_grid_units":str(30/duration),
                      "annual_rate_from_printed_day_hint_360_days_per_year":str(F(360,day_hint)),
                      "untraveled_units_under_printed_rate_at_period_end":str(30-duration*literal)})
    result = {
        "registration_sha256":args.registration_sha256,
        "transcription_sha256":args.transcription_sha256,
        "version":spec["version"],
        "grid_cell_count":sum(len(row) for row in GRID.values()),
        "solar_palace_hour_combinations":sum(ming_palace(s,h) in BRANCHES for s in BRANCHES for h in BRANCHES),
        "frame_cycle_units": {k:str(frame.cycle) for k,frame in frames.items()},
        "gujin_transfers":transfers, "gujin_limits":limits, "xingxue_zi_limits":zi_extended,
        "xingxue_wing_example": {"source":wing,"grid":wing_grid,
                                 "continuous":project(frames,*wing["solar"],derived_ming),
                                 "printed_schedule_comparison":entries},
        "printed_versus_normalized_annual_rates":rates,
    }
    with args.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registration-sha256",required=True)
    p.add_argument("--transcription-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
