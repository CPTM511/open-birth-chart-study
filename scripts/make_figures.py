#!/usr/bin/env python3
"""Render shareable figures from published aggregate JSON, without raw births."""
from pathlib import Path
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

NAMES={'ogdb2023':'OGDB historical','brazil2006':'Brazil 2006','adb_z2026':'ADB Z reference'}
COLORS={'bazi':'#166E82','ziwei':'#B66A2B','qizheng':'#6E5AA7','western':'#238B65'}
ORDER=['ogdb2023','brazil2006','adb_z2026']


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',default='results');p.add_argument('--output',default='figures')
    args=p.parse_args();d=Path(args.results);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    r=json.loads((d/'structural_results.json').read_text())
    sen=json.loads((d/'sensitivity_results.json').read_text())
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'axes.labelcolor':'#203342','text.color':'#203342',
        'xtick.color':'#425461','ytick.color':'#425461','figure.facecolor':'white','savefig.facecolor':'white'})
    def save(fig,name):
        fig.savefig(out/(name+'.png'),dpi=180,bbox_inches='tight')
        fig.savefig(out/(name+'.svg'),bbox_inches='tight')
        plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.7),gridspec_kw={'width_ratios':[1,1.7]})
    y=np.arange(3)
    axes[0].barh(y,[r['sources'][s]['source_records'] for s in ORDER],color=['#7896A4','#166E82','#C49B63'])
    axes[0].set_yticks(y,[NAMES[s] for s in ORDER]);axes[0].invert_yaxis()
    axes[0].set_xlim(0,2400);axes[0].set_xlabel('Records scored in four systems')
    for i,s in enumerate(ORDER):
        entry=r['sources'][s]
        axes[0].text(entry['source_records']+30,i,f"{entry['source_records']:,}",va='center')
    decades=list(range(1880,2020,10));bottom=np.zeros(len(decades))
    for source,color in zip(ORDER,['#7896A4','#166E82','#C49B63']):
        values=np.array([r['sources'][source]['birth_decade_counts'].get(str(a),0) for a in decades])
        axes[1].bar(decades,values,width=8,bottom=bottom,color=color,label=NAMES[source]);bottom+=values
    axes[1].set_xticks(decades,[str(x) for x in decades],rotation=55,ha='right')
    axes[1].set_ylabel('Sample records');axes[1].set_xlabel('Birth decade');axes[1].legend(frameon=False,fontsize=9)
    fig.suptitle('3,729 records; 32 country labels; strongly uneven coverage',fontsize=16,x=.06,ha='left')
    fig.text(.06,.01,'The large modern cohort is Brazil 2006. Country coverage does not establish global representativeness.',fontsize=10)
    fig.tight_layout(rect=[0,.07,1,.92]);save(fig,'01_sample_coverage')

    fig,ax=plt.subplots(figsize=(11,5.5));labels=[]
    for source in ORDER:
        for window in ['age20_59','age20_49']:
            t=r['sources'][source]['tests'][window];i=len(labels)
            labels.append(NAMES[source]+' / '+('20–59' if window=='age20_59' else '20–49'))
            lo,hi=np.array(t['phase_reference_interval95'])*100
            ax.plot([lo,hi],[i,i],color='#AAB8C3',lw=7,solid_capstyle='round',label='95% phase-reference interval' if i==0 else None)
            ax.plot(t['exact_independent_phase_mean']*100,i,'|',color='#3A4E5D',ms=17,mew=1.6,label='Exact phase-reference mean' if i==0 else None)
            ax.plot(t['weighted_concordance']*100,i,'o',color='#C25C36',ms=7,label='Observed model alignment' if i==0 else None)
    ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_xlabel('Record-years with at least 3 of 4 relative signals elevated (%)')
    ax.set_title('Observed alignment versus the frozen phase reference',loc='left',fontsize=15,pad=16)
    ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True);ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,-.16),ncol=3,fontsize=9)
    fig.text(.04,.015,'A structural test only. The interval is not a confidence interval for death risk or a forecast of real events.',fontsize=10)
    fig.tight_layout(rect=[0,.1,1,1]);save(fig,'02_phase_reference')

    fig,axes=plt.subplots(2,2,figsize=(12,7.7),sharex='col')
    for col,source in enumerate(['brazil2006','adb_z2026']):
        ann=r['sources'][source]['annual_2026_2070'];years=[x['year'] for x in ann]
        n=np.array([x['people'] for x in ann])
        for system,color in COLORS.items():
            val=[(x['mean_within_person_percentiles'] or {}).get(system,np.nan) for x in ann]
            axes[0,col].plot(years,val,lw=1.7,color=color,label=system.capitalize())
        axes[0,col].set_title(NAMES[source],loc='left',fontsize=13);axes[0,col].set_ylim(0,1)
        axes[0,col].set_ylabel('Mean within-person percentile')
        joint=np.array([np.nan if x['concordance'] is None else 100*x['concordance'] for x in ann])
        axes[1,col].plot(years,joint,color='#203342',lw=1.8)
        axes[1,col].scatter(np.array(years)[n<30],joint[n<30],s=20,facecolor='white',edgecolor='#203342',zorder=3,label='Fewer than 30 records')
        axes[1,col].set_ylabel('At least 3 signals elevated (%)');axes[1,col].set_xlabel('Calendar year');axes[1,col].set_ylim(bottom=0)
        axes[1,col].set_title('Eligible records only, completed ages 20–59',fontsize=10,loc='left')
        for ax in axes[:,col]:ax.grid(axis='y',alpha=.15);ax.set_xlim(2026,2070)
        nonzero=[x for x in ann if x['people']]
        axes[1,col].text(.02,.95,f"Annual sample n: {min(x['people'] for x in nonzero)}–{max(x['people'] for x in nonzero):,}",transform=axes[1,col].transAxes,va='top',fontsize=9)
    axes[0,0].legend(frameon=False,ncol=2,fontsize=9);axes[1,1].legend(frameon=False,fontsize=8,loc='upper left',bbox_to_anchor=(.015,.86))
    fig.suptitle('2026–2070: calendar curves are model outputs',fontsize=16,x=.06,ha='left')
    fig.text(.06,.02,'Historical OGDB has no age-eligible records in this window. Gaps mean no eligible records, not zero signal or death.',fontsize=9.7)
    fig.tight_layout(rect=[0,.065,1,.95]);save(fig,'03_calendar_profiles')

    fig,axes=plt.subplots(1,3,figsize=(12,4.9),sharey=True)
    shifts=['clock_-120','clock_-30','clock_+30','clock_+120']
    for ax,source in zip(axes,ORDER):
        groups={x['variant']:x for x in sen['groups'] if x['source']==source}
        for i,system in enumerate(COLORS):
            vals=[100*groups[v]['systems'][system]['elevated_flag_flip_fraction'] for v in shifts]
            ax.plot(range(4),vals,'o-',label=system.capitalize(),color=COLORS[system],lw=1.6,ms=4)
        ax.plot(range(4),[100*groups[v]['concordance_flag_flip_fraction'] for v in shifts],'s--',color='#203342',label='3-of-4 joint',lw=1.5,ms=4)
        ax.set_xticks(range(4),['−120','−30','+30','+120']);ax.set_xlabel('Clock shift (minutes)');ax.set_title(NAMES[source],fontsize=12,loc='left');ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('Relative signal classifications changed (%)')
    axes[-1].legend(frameon=False,fontsize=8.5,ncol=2)
    fig.suptitle('Birth-time stress tests: sensitivity of the chosen models',fontsize=16,x=.06,ha='left')
    fig.text(.06,.02,'200 preselected records per source; 40 annual points each. Fixed stress points are not measured birth-time error bounds.',fontsize=9.5)
    fig.tight_layout(rect=[0,.08,1,.93]);save(fig,'04_clock_sensitivity')
    print(json.dumps({'figures':8,'directory':str(out)}))


if __name__=='__main__':main()
