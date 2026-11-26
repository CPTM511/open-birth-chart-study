#!/usr/bin/env python3
"""Post-result descriptive calendar mechanism, not a registered significance test."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import argparse, json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from open_birth_chart import bazi_engine as b
from open_birth_chart.io import load_source
from lunar_python import Solar

def main():
    p=argparse.ArgumentParser();p.add_argument('--sample',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rows,m=load_source(a.sample)
    if m['source']!='brazil2006':raise ValueError('This descriptive check concerns the Brazil 2006 cohort')
    c=Counter();w=Counter()
    for row in rows:
        branch=b.build_natal(row)['pillars']['year']['branch']
        c[branch]+=1;w[branch]+=row['sample_weight']
    result={'created_utc':datetime.now(timezone.utc).isoformat(),
        'analysis_type':'post-result descriptive mechanism check, not preregistered test',
        'n':len(rows),'natal_year_branch_counts':dict(c),'natal_year_branch_weight_sum':dict(w),
        'calendar_year_pillars':{str(y):Solar.fromYmdHms(y,7,1,12,0,0).getLunar().getEightChar().getYear() for y in [2036,2048,2060]},
        'interpretation':'The selected Bazi index counts opposite branches. The repeated Chen years oppose the common Xu birth-year branch. This mechanically supplies a shared contact term; it is not a calibrated real-event risk or an exhaustive explanation of the joint peak.',
        'new_p_values':False,'source_input_sha256':m['model_input_sha256']}
    path=Path(a.output)
    if path.exists():raise FileExistsError('Preserve the original descriptive output; choose a new file')
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
