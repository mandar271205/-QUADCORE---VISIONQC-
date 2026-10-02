"""Wait for the primary suite, then complete 30-shot/depth jobs and report.

Already-running downloads and training remain independent processes. This
supervisor writes pending/failed/complete status without inventing metrics.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
EXPECTED=[i for i in json.loads((ROOT/'experiments/datasets.json').read_text()) if i['dataset']!='d2s']
STATE={}


def state(**fields):
    STATE.update(fields)
    temporary=OUT/'experiment_status.tmp';temporary.write_text(json.dumps(STATE,indent=2)+'\n')
    temporary.replace(OUT/'experiment_status.json')
    print(fields,flush=True)


def run_script(name,log,args=()):
    state(phase=name)
    with open(log,'a') as output:
        result=subprocess.run([sys.executable,str(ROOT/'experiments'/name),*args],cwd=ROOT,
                              env={**os.environ,'PYTHONPATH':str(ROOT/'backend'),'PYTORCH_ENABLE_MPS_FALLBACK':'1'},
                              stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'{name} failed with exit code {result.returncode}; see {log}')


def check_d2s_failure():
    path=OUT/'d2s/status.json'
    if path.exists():
        segmentation=json.loads(path.read_text())
        if segmentation.get('state')=='failed':
            raise RuntimeError('D2S training failed: '+segmentation.get('error','unknown error')+
                               '; see /tmp/visionqc-d2s-training.log')


def report():
    anomaly=json.loads((OUT/'training_f2/final_results.json').read_text())
    rows=[row for category in anomaly for row in category['final_results'] if row['selected_for_deployment']]
    selected=[]
    for row in rows:
        improved=OUT/'improved_f2'/row['dataset']/row['category']/'results.json'
        if improved.exists():
            improved_report=json.loads(improved.read_text())
            row={**row,**improved_report['final_metrics'],'model':'ensemble',
                 'parameters':improved_report['selected']}
        selected.append({key:row.get(key) for key in ('dataset','category','model','accuracy','balanced_accuracy','f2','f1',
                        'precision','recall','image_auroc','pixel_auroc','average_precision','false_accept_rate',
                        'false_reject_rate','latency_ms','training_images','test_images','parameters','confusion_matrix')})
    depth=[json.loads(path.read_text()) for path in sorted((OUT/'depth_f2').glob('*/results.json'))]
    d2s=json.loads((OUT/'d2s/results.json').read_text())
    comparison=json.loads((OUT/'30shot_f2/results.json').read_text())
    macro={key:sum(row[key] for row in selected if row[key] is not None)/
               sum(row[key] is not None for row in selected)
           for key in ('accuracy','balanced_accuracy','f2','f1','precision','recall','image_auroc')}
    tn=sum(row['confusion_matrix'][0][0] for row in selected)
    fp=sum(row['confusion_matrix'][0][1] for row in selected)
    fn=sum(row['confusion_matrix'][1][0] for row in selected)
    tp=sum(row['confusion_matrix'][1][1] for row in selected)
    micro={'confusion_matrix':[[tn,fp],[fn,tp]],'test_images':tn+fp+fn+tp,
           'accuracy':(tn+tp)/max(1,tn+fp+fn+tp),'precision':tp/max(1,tp+fp),
           'recall':tp/max(1,tp+fn),'f1':2*tp/max(1,2*tp+fp+fn),
           'f2':5*tp/max(1,5*tp+fp+4*fn)}
    document={'selection_metric':'development F2 (beta=2)','anomaly_selected_models':selected,
              'anomaly_category_macro_metrics':macro,'anomaly_pooled_decision_metrics':micro,
              'aggregation_scope':'Selected anomaly models only; category macro gives each category equal weight; pooled decisions give each test image equal weight. D2S and depth comparisons are separate.',
              'downloads':json.loads((ROOT/'data/download_status.json').read_text()),
              'improved_models':[json.loads(path.read_text()) for path in sorted((OUT/'improved_f2').glob('*/*/results.json'))],
              'roi_experiments':[json.loads(path.read_text()) for path in sorted((OUT/'roi').glob('*/*/results.json'))],
              'all_anomaly_trials_and_models':anomaly,'comparison_30shot':comparison,
              'depth':depth,'segmentation':d2s,'evaluation_limitations':[
                  'Final scores are from frozen local held-out splits, not official full-test scores.',
                  'Frozen final splits were evaluated in earlier runs, including core refinement. Selection uses development F2 only; these are repeated local evaluations, not fresh unseen benchmark tests.',
                  'D2S official test annotations and AD2 private test ground truth are unavailable locally.',
                  'Best means best development F2 among recorded candidates; a global optimum is not established.']}
    (OUT/'FINAL_RESULTS.json').write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')
    lines=['# VisionQC final F2-focused results','',
           'Selected on development F2; evaluated on frozen held-out local splits. Scores are percentages except latency.',
           '', '| Dataset | Category | Model | F2 | Recall | Precision | F1 | Accuracy | Image AUROC | Pixel AUROC | FAR | FRR | ms/image |',
           '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    def display(value):return 'Unavailable' if value is None else f'{value*100:.2f}'
    for row in selected:
        values=[row['dataset'],row['category'],row['model']]+[display(row[k]) for k in
                ('f2','recall','precision','f1','accuracy','image_auroc','pixel_auroc','false_accept_rate','false_reject_rate')]+[f"{row['latency_ms']:.2f}"]
        lines.append('| '+' | '.join(values)+' |')
    lines.extend(['','## Aggregated anomaly decisions','',
                  f"Equal-weight category macro: F2 **{display(macro['f2'])}%**, recall {display(macro['recall'])}%, precision {display(macro['precision'])}%, F1 {display(macro['f1'])}%, accuracy {display(macro['accuracy'])}%.",
                  '',f"Pooled across {micro['test_images']} held-out anomaly images: F2 **{display(micro['f2'])}%**, recall {display(micro['recall'])}%, precision {display(micro['precision'])}%, F1 {display(micro['f1'])}%, accuracy {display(micro['accuracy'])}%.",
                  '', 'These aggregates combine selected category models; they exclude D2S and depth comparisons. They are not official benchmark scores.',
                  '', 'Confusion matrices use [[true normals, rejected normals], [missed defects, detected defects]]. FAR is missed defects / defects; FRR is rejected normals / normals.',
                  '', '## Separate 30-shot comparison','',
                  '| Category | Model | F2 | Recall | Precision | F1 | Accuracy | Image AUROC |',
                  '|---|---|---:|---:|---:|---:|---:|---:|'])
    for row in comparison:
        values=[row['category'],row['model']]+[display(row[k]) for k in ('f2','recall','precision','f1','accuracy','image_auroc')]
        lines.append('| '+' | '.join(values)+' |')
    lines.extend(['','## Aligned depth and RGB/depth fusion','',
                  '| Category | Pipeline | F2 | Recall | Precision | F1 | Accuracy | Image AUROC |',
                  '|---|---|---:|---:|---:|---:|---:|---:|'])
    for category in depth:
        for label,key in (('Depth prototype','depth_final'),('Development-selected RGB/depth fusion','fusion_final')):
            metrics=category[key]
            values=[category['category'],label]+[display(metrics[k]) for k in ('f2','recall','precision','f1','accuracy','image_auroc')]
            lines.append('| '+' | '.join(values)+' |')
    lines.extend(['','## D2S segmentation','',f"Original COCO mask metrics: `{json.dumps(d2s['final_metrics'])}`",'',
                  'Official D2S test metrics require private annotations; no image-classification accuracy is assigned to segmentation.',
                  '', 'All parameter trials, thresholds, audits, predictions, confusion matrices, and individual model metrics are retained in `FINAL_RESULTS.json` and category output directories.',
                  '', '## Evaluation limits',''])
    lines.extend('- '+item for item in document['evaluation_limitations'])
    (OUT/'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    OUT.mkdir(exist_ok=True);state(state='running',phase='waiting_for_primary_training',selection_metric='F2')
    try:
        while True:
            check_d2s_failure()
            worker_path=OUT/'primary_worker_status.json'
            if worker_path.exists():
                worker=json.loads(worker_path.read_text())
                if worker.get('state')=='failed':
                    raise RuntimeError('Primary worker failed: '+worker.get('error','unknown error')+
                                       '; see /tmp/visionqc-primary-resume.log')
            status_path=OUT/'training_f2/status.json'
            status=json.loads(status_path.read_text()) if status_path.exists() else {}
            keys=[i['dataset']+'/'+i['category'] for i in EXPECTED]
            if all(status.get(key,{}).get('state') in ('complete','failed') for key in keys):
                failures={key:status[key] for key in keys if status[key]['state']=='failed'}
                if failures:raise RuntimeError('Primary training failures: '+json.dumps(failures))
                break
            download_path=ROOT/'data/download_status.json'
            downloads=json.loads(download_path.read_text()) if download_path.exists() else {}
            failures={key:v for key,v in downloads.items() if v['state']=='failed'}
            if failures:raise RuntimeError('Download failures: '+json.dumps(failures))
            time.sleep(30)
        run_script('train_30shot.py','/tmp/visionqc-30shot-training.log')
        run_script('improve_models.py','/tmp/visionqc-improve.log')
        run_script('export_profiles.py','/tmp/visionqc-export.log',('--seed-products',))
        run_script('run_roi_suite.py','/tmp/visionqc-roi.log')
        run_script('train_depth_suite.py','/tmp/visionqc-depth-training.log')
        state(phase='waiting_for_d2s_final_report')
        while not (OUT/'d2s/results.json').exists():
            check_d2s_failure()
            time.sleep(30)
        d2s=json.loads((OUT/'d2s/results.json').read_text())
        run_script('run_roi_suite.py','/tmp/visionqc-d2s-roi.log',
                   ('--yolo-weights',str(ROOT/d2s['selected']['checkpoint'])))
        downloads=json.loads((ROOT/'data/download_status.json').read_text())
        if len(downloads)!=18 or any(v['state']!='complete' for v in downloads.values()):
            raise RuntimeError('Not all 18 document archives are complete')
        report();state(state='complete',phase='final_report',report='outputs/FINAL_REPORT.md',results='outputs/FINAL_RESULTS.json')
    except Exception as error:
        state(state='failed',error=str(error));raise
