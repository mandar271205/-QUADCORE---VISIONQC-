"""Publish small, genuine benchmark summaries without datasets or model weights."""
import argparse
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('f2','accuracy','precision','recall','f1','balanced_accuracy','image_auroc','pixel_auroc',
        'average_precision','false_accept_rate','false_reject_rate','latency_ms','confusion_matrix')


def build(require_complete=False):
    state=json.loads((ROOT/'outputs/experiment_status.json').read_text())
    complete=state.get('state')=='complete'
    if require_complete and not complete:
        raise RuntimeError('The complete experiment suite has not finished')
    catalog=json.loads((ROOT/'models/catalog.json').read_text())
    comparisons=json.loads((ROOT/'outputs/30shot_f2/results.json').read_text())
    depth=[json.loads(p.read_text()) for p in sorted((ROOT/'outputs/depth_f2').glob('*/results.json'))]
    roi=[]
    for p in sorted((ROOT/'outputs/roi').glob('*/*/results.json')):
        r=json.loads(p.read_text())
        roi.append({k:r.get(k) for k in ('category','extractor','evaluation_scope','mode','full_frame_metrics',
                    'roi_metrics','roi_metrics_unavailable','note')})
    d2s_path=ROOT/'outputs/d2s/results.json'
    d2s=json.loads(d2s_path.read_text()) if d2s_path.exists() else None
    if complete and (len(catalog)!=16 or len(comparisons)!=9 or len(depth)!=3 or d2s is None):
        raise RuntimeError('Completion status disagrees with expected result artifacts')
    rows=[{'dataset':p['dataset'],'category':p['category'],**{k:p['metrics'].get(k) for k in FIELDS}}
          for p in catalog.values()]
    result={'status':'complete' if complete else 'partial; D2S training/final evaluation pending',
            'selection':'development F2; final labels are not used to select parameters or thresholds',
            'limitations':['Frozen final splits have been evaluated in earlier runs; these are repeated local evaluations.',
                           'Category-specific benchmark profiles require matching product and image conditions.',
                           'High F2 can coexist with unacceptable normal-image rejection; inspect FAR and FRR.',
                           'D2S grocery segmentation is a domain ablation for industrial parts.',
                           'Physical cameras and phone networking have not been tested.'],
            'anomaly_models':rows,
            'parameters':{key:p.get('checkpoint_parameters') for key,p in catalog.items()},
            'comparison_30shot':[{k:r.get(k) for k in ('dataset','category','model',*FIELDS)} for r in comparisons],
            'depth':[{'category':r['category'],'depth':r['depth_final'],'fusion':r['fusion_final'],
                      'latency_scope':r.get('latency_scope')} for r in depth],
            'roi':roi,'d2s':None if d2s is None else {'metrics':d2s['final_metrics'],
                  'selected_parameters':d2s['selected']['parameters'],'protocol':d2s['protocol'],
                  'accuracy':None,'accuracy_reason':d2s['accuracy_reason']}}
    folder=ROOT/'docs/results';folder.mkdir(parents=True,exist_ok=True)
    (folder/'metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (folder/'anomaly_metrics.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    percent=lambda value:'Unavailable' if value is None else f'{100*value:.2f}%'
    lines=['# Recorded VisionQC results','',f"Status: **{result['status']}**.",'',
           'Selected using development F2. The rows below are actual frozen local final evaluations. Defects are positive.',
           '', '| Dataset | Category | F2 | Accuracy | Precision | Recall | F1 | FAR | FRR |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| '+' | '.join([row['dataset'],row['category']]+[percent(row[k]) for k in
                     ('f2','accuracy','precision','recall','f1','false_accept_rate','false_reject_rate')])+' |')
    lines+=['','FAR = missed defects / defects; FRR = rejected normal images / normals. Profiles with high FRR are experimental and unsuitable for reliable automatic acceptance without further work.',
            '', 'Full metrics, confusion matrices, recorded parameters, nine 30-shot comparisons, depth results and ROI ablations are in [metrics.json](metrics.json). Benchmark latency differs from CPU API request latency.',
            '', '## D2S segmentation','']
    if d2s:
        m=d2s['final_metrics']
        lines.append('Original-mask F2: '+percent(m['mask_f2'])+'; precision: '+percent(m['mask_precision'])+
                     '; recall: '+percent(m['mask_recall'])+'; F1: '+percent(m['mask_f1'])+'.')
    else:
        lines.append('Training is still running. No final segmentation metrics are available yet.')
    lines+=['','## Evaluation limits','']+['- '+item for item in result['limitations']]
    lines+=['','See [the training runbook](../TRAINING_F2.md) and [deployment guide](../DEPLOYMENT.md) for reproducibility and integration checks. Datasets, weights and bulk example images stay outside Git.']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    print(result['status'],len(rows),'anomaly profiles',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--require-complete',action='store_true')
    build(parser.parse_args().require_complete)
