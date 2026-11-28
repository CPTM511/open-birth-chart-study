"""Verify literal-coverage evidence, archive hash, and original worked example."""

import argparse
from fractions import Fraction
from pathlib import Path

from rounds.r45.common import digest, read_json, require, write_json
from .coverage import REGISTRATION, registered


def review(result, replay, scan, destination):
    spec = registered()
    require(digest(scan)==spec["bazi_source"]["pdf_sha256"],"Wrong original scanned copy")
    current,repeated = read_json(result),read_json(replay)
    require(current==repeated and current["registration"]==REGISTRATION,"Literal-period replay differs")
    # NLC416 copy of San Ming Tong Hui, printed juan 2 page 37.
    # Five days and three two-hour periods are 63 periods.
    traditional_hours = 5*12 + 3
    start = Fraction(traditional_hours,3*12)
    require(traditional_hours==63 and start==Fraction(7,4),"Historical worked example differs")
    check = {"input_count":0,"checked_bazi_intervals":0,"checked_ziwei_intervals":0}
    for group,n in spec["r45_records"].items():
        found = current["groups"][group]
        require(found["complete_inputs"]==n and found["bazi_periods"]==n*spec["bazi_expected_decades"]
                and found["ziwei_periods"]==n*spec["ziwei_expected_decades"],"Wrong complete-period total")
        require(found["observed_gap_or_overlap"]==0
                and found["bazi_scores_with_unique_period"]==40*n
                and found["ziwei_nominal_ages_with_unique_palace"]==43*n
                and found["qizheng_monthly_snapshots_in_schedule"]==480*n,"Data coverage proof is incomplete")
        require(found["neighbor_start_palace_changes"]==43*n
                and found["ziwei_annual_replay_matches"]==40*spec["ziwei_july_snapshot_replay_per_group"],
                "Ziwei cycle validation is incomplete")
        check["input_count"] += n
        check["checked_bazi_intervals"] += found["bazi_periods"]
        check["checked_ziwei_intervals"] += found["ziwei_periods"]
    write_json(destination,{"registration":REGISTRATION,"result_sha256":digest(result),"replay_sha256":digest(replay),
                            "scoring_replay_exact":True,"independent_calendar_and_age_index_checks":check,
                            "historical_example":{"scan_pdf_page_one_based":115,
                                "transmitted_original_has_both_day_and_hour_labels":True,
                                "input_traditional_hours":traditional_hours,"start_years_exact":str(start),
                                "ten_year_next_step_age_exact":str(start+10)}})


if __name__=="__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("results","replay","scan","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    review(args.results,args.replay,args.scan,args.output)
