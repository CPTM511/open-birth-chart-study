"""Render aggregate-only R9 figures; never load individual birth profiles."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE/'structural_comparison.json').read_text())
targets = sorted(data['targets'], key=lambda x: x['slot'])
labels = {'brazil2016':'Brazil 2016', 'mexico2015':'Mexico 2015'}
colors = ['#137C83', '#B05B29']
plt.rcParams.update({'font.size':11, 'axes.spines.top':False,
    'axes.spines.right':False, 'savefig.facecolor':'white', 'svg.hashsalt':'OBS-R9'})

fig, ax = plt.subplots(figsize=(9.8,4.8), layout='constrained')
for i, (target, color) in enumerate(zip(targets, colors)):
    point = target['delta_joint_rate']*100
    lo, hi = np.array(target['sampling_interval']['delta_joint_family_adjusted_interval'])*100
    lo95, hi95 = np.array(target['sampling_interval']['delta_joint_interval95'])*100
    ax.plot([lo,hi], [i,i], color=color, linewidth=2)
    ax.plot([lo95,hi95], [i,i], color=color, linewidth=7, solid_capstyle='butt')
    ax.plot(point,i,'o', color=color, markersize=9)
    ax.annotate(f'{point:+.3f} pp  [{lo:+.3f}, {hi:+.3f}]', (point,i),
        xytext=(0,19), textcoords='offset points', ha='center', fontsize=11)
ax.axvline(0, color='#64748b', linewidth=1, linestyle='--')
ax.set_yticks(range(len(targets)), [labels[t['slot']]+' (n=2,000)' for t in targets])
ax.set_ylim(-0.55,1.65)
ax.set_xlabel('Difference in joint high-score rate vs fixed Brazil 2006 reference (percentage points)')
ax.set_title('Frozen-model structural comparison: completed ages 20–59', loc='left', weight='bold', pad=16)
ax.grid(axis='x', alpha=.18)
fig.text(.01,-.045,'Thin: 98.33% per-slot interval (three-slot family); thick: 95%. Fixed reference; eligible-frame sampling only.\nNot an event probability. Source selection, clock/location error and model validity are outside these intervals.', fontsize=9, color='#475569')
for suffix in ['png','svg']:
    fig.savefig(HERE/f'cohort_contrasts.{suffix}',dpi=180,bbox_inches='tight',metadata={'Date':None} if suffix=='svg' else {})
plt.close(fig)

fig, ax = plt.subplots(figsize=(10,5.2), layout='constrained')
all_sources = [data['reference']] + targets
for row,label,color in zip(all_sources, ['Brazil 2006 reference']+[labels[t['slot']] for t in targets], ['#64748b']+colors):
    calendar = row['calendar_2026_2070']
    years = [r['year'] for r in calendar]
    values = [np.nan if r['eligible_source_records']<30 else r['joint_rate']*100 for r in calendar]
    ax.plot(years,values,label=label,color=color,linewidth=1.7)
ax.set_xlim(2026,2070)
ax.set_ylim(bottom=0)
ax.set_xlabel('Calendar year (July 1 completed-age convention)')
ax.set_ylabel('Source-weighted joint high-score rate (%)')
ax.set_title('Descriptive calendar view: structural scores, not validated forecasts',loc='left',weight='bold',pad=14)
ax.legend(frameon=False,loc='upper left')
ax.grid(alpha=.15)
fig.text(.01,-.045,'Only included ages 20–59 are shown; gaps are unobserved model coverage, never zero or death.\nNo peak-year hypothesis test. Different cohorts have different ages in the same year; calendar and cohort effects remain confounded.',fontsize=9,color='#475569')
for suffix in ['png','svg']:
    fig.savefig(HERE/f'calendar_view.{suffix}',dpi=180,bbox_inches='tight',metadata={'Date':None} if suffix=='svg' else {})
plt.close(fig)
