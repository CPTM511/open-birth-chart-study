"""Choose refit draw budget from synthetic runtime before R10 target scores."""
from pathlib import Path
import hashlib,json,platform,time
import numpy as np
from reference_sensitivity import run_sensitivity
from check_methods import checks


def main():
    check=checks();rng=np.random.default_rng(202611271010)
    n=2000;strata=np.array([f'S{i%54:02d}' for i in range(n)])
    frames={s:int((strata==s).sum())*1000 for s in set(strata)}
    def source():
        raw=rng.uniform(size=(n,40,4));raw[:,:,0]=np.round(raw[:,:,0]*8)/8;raw[:,:,1]=np.round(raw[:,:,1]*2)/2
        return {'scores':raw,'weights':np.full(n,1000.),'strata':strata,'frame_counts':frames}
    ref=source();targets={f'slot{i}':source() for i in range(7)};started=time.monotonic()
    run_sensitivity(ref,targets,draws=10,reference_seed=202611271020,target_seeds={name:202611271030+i for i,name in enumerate(sorted(targets))})
    elapsed=time.monotonic()-started;projected=elapsed*999/10;selected=999 if projected<=120 else 199;p=Path(__file__).parent
    report={'real_R10_targets_inspected':False,'synthetic_records_per_source':n,'target_slots':7,'strata_per_source':54,'benchmark_draws':10,
        'elapsed_seconds':elapsed,'conservative_projected_seconds_for_999':projected,'budget_decision_threshold_seconds':120,'selected_refit_draws':selected,
        'decision_rule':'999 if linear projection including setup <=120 seconds, else199; frozen before target inspection; no effect-dependent timing choice',
        'primary_draws':9999,'family_size':7,'method_checks':check,'runtime':{'python':platform.python_version(),'numpy':np.__version__},
        'code_sha256':{name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ['reference_sensitivity.py','threshold_precision.py','precision_reference.py','check_methods.py','benchmark_refit.py']},
        'interpretation':'Runtime test and numerical controls only; no bootstrap coverage guarantee for discrete threshold scores.'}
    (p/'refit_benchmark.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'benchmark_seconds':elapsed,'projected_999':projected,'selected_draws':selected,'checks':check['count']}))


if __name__=='__main__':main()
