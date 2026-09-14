"""Offline paper figure from the reviewed matched-evidence analysis; no inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

MODELS=('qwen3:0.6b','qwen3:1.7b')
CATS=('routine_general','constrained_general','personal_recall','personal_temporal')
LABELS=('Routine general','Several constraints','Personal recall','Temporal / synthesis')
OUTCOMES=('both_correct','only_small_correct','only_large_correct','neither_correct')

def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    d=a.output.absolute();d.mkdir(mode=0o700,exist_ok=False)
    data=json.loads((a.analysis/'analysis.json').read_text())
    rows=[json.loads(s) for s in (a.analysis/'scored_answers.jsonl').read_text().splitlines()]
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,(ax,bx)=plt.subplots(1,2,figsize=(11,4.4),gridspec_kw={'width_ratios':[1.15,1]})
    left=[0]*4;colors=['#8da9b8','#e5aa51','#529b76','#d8d8d8']
    for outcome,label,color in zip(OUTCOMES,('Both correct','Only 0.6B','Only 1.7B','Neither'),colors):
        values=[data['pair_counts'][c][outcome] for c in CATS]
        ax.barh(range(4),values,left=left,color=color,label=label,height=.63)
        for j,(n,l) in enumerate(zip(values,left)):
            if n:ax.text(l+n/2,j,str(n),ha='center',va='center',fontsize=9)
        left=[l+n for l,n in zip(left,values)]
    ax.set_yticks(range(4),LABELS);ax.invert_yaxis();ax.set_xlim(0,30);ax.set_xlabel('Matched requests (30 per category)');ax.set_title('Assistant-reviewed full-rubric correctness')
    ax.legend(loc='lower center',bbox_to_anchor=(.5,-.4),ncol=2,frameon=False)
    for model,color in zip(MODELS,('#c58227','#337c57')):
        values=sorted(r['transport']['wall_ns']/1e9 for r in rows if r['model']==model and 'wall_ns' in r['transport'])
        bx.step([0]+values,[0]+[(i+1)/120 for i in range(len(values))],where='post',color=color,label=model,lw=2)
    bx.set_xlabel('Warm request wall time (seconds)');bx.set_ylabel('Fraction of all 120 attempts');bx.set_ylim(0,1.03);bx.set_title('All outcomes retained; preload separate');bx.legend(frameon=False,loc='lower right')
    fig.subplots_adjust(left=.16,right=.98,wspace=.48,bottom=.29,top=.85)
    fig.suptitle('CLARA matched-evidence generator capability',fontsize=14,y=.99)
    fig.text(.5,.01,'One frozen 120-case workload; 240 attempts. Independent human validation pending.',ha='center',fontsize=9)
    for suffix in ('png','pdf','svg'):fig.savefig(d/f'paired_capability.{suffix}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    with (d/'paired_outcomes.csv').open('x') as s:
        w=csv.writer(s);w.writerow(['category',*OUTCOMES]);w.writerows([c,*[data['pair_counts'][c][o] for o in OUTCOMES]] for c in CATS)
    with (d/'attempt_latency.csv').open('x') as s:
        w=csv.writer(s);w.writerow(['request_id','model','category','status','correct','wall_seconds'])
        w.writerows([r['request_id'],r['model'],r['category'],r['status'],r['correct'],r['transport'].get('wall_ns',0)/1e9] for r in rows)
    shutil.copyfile(__file__,d/'render_source.py')
    hashes={str(p.relative_to(a.analysis)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.analysis.iterdir() if p.is_file()}
    (d/'provenance.json').write_text(json.dumps({'analysis':str(a.analysis.resolve()),'input_sha256':hashes,'python':sys.version,'matplotlib':matplotlib.__version__,'scope':'offline presentation of frozen reviewed analysis'},indent=2)+'\n')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir() if p.is_file()}
    (d/'seal.json').write_text(json.dumps({'sha256':manifest},indent=2)+'\n')
    for p in d.iterdir():p.chmod(0o400)
    d.chmod(0o500)
    print(d)

if __name__=='__main__':main()
