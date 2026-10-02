"""Resumable real-data search. Final labels never select models/thresholds.

Run from repo root: PYTHONPATH=backend PYTORCH_ENABLE_MPS_FALLBACK=1
.venv/bin/python -u experiments/train_suite.py
"""
import argparse
import gc
import hashlib
import json
import os
import random
import shutil
import fcntl
import time
import traceback
from dataclasses import asdict
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import fbeta_score,roc_auc_score
from data_protocol import prepare,canonical_training,mask_array
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.preprocessing import read_rgb
from app.services.ml.shared.result import calibrate
from app.services.ml.shared.metrics import evaluate
from app.services.ml.factory import model_class
from app.services.ml.comparison import write_csv

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
OUT=ROOT/'outputs/training_f2'
PRIOR=ROOT/'outputs/training'
STATUS={}


def update(key,**fields):
    STATUS.setdefault(key,{}).update(fields)
    temp=OUT/'status.tmp'; temp.write_text(json.dumps(STATUS,indent=2,allow_nan=False)+'\n')
    temp.replace(OUT/'status.json')
    print(key,fields,flush=True)


def release():
    gc.collect()
    if torch.backends.mps.is_available(): torch.mps.empty_cache()


def score_samples(model,base,samples,*,save=None):
    scores,latencies,masks,maps,predictions=[],[],[],[],[]
    selected=set()
    if save:
        rng=random.Random(42)
        for label in (0,1):
            pool=[i['filename'] for i in samples if i['label']==label]
            selected.update(rng.sample(pool,min(5,len(pool))))
    for item in samples:
        heatmap=None
        if save and item['filename'] in selected:
            heatmap=save/'examples'/Path(item['filename']).with_suffix('.png')
        result,amap=model.predict(base/item['filename'],heatmap)
        scores.append(result.anomaly_score); latencies.append(result.latency_ms)
        masks.append(mask_array(base,item,model.config.image_size)); maps.append(amap)
        predictions.append({**result.to_dict(),'filename':item['filename'],'ground_truth':item['label']})
    metrics=evaluate([i['label'] for i in samples],scores,model.threshold,latencies,masks,maps)
    return metrics,predictions


def choose_threshold(normal_scores,validation_labels,validation_scores):
    # GOOD-only percentile thresholds; labelled development chooses the percentile.
    candidates=[]
    for percentile in (90,95,97.5,99,99.5,100):
        threshold=calibrate(normal_scores,percentile)
        f2=float(fbeta_score(validation_labels,np.asarray(validation_scores)>threshold,beta=2,zero_division=0))
        candidates.append((f2,percentile,threshold))
    unique=np.unique(validation_scores)
    labelled_thresholds=np.concatenate(([np.finfo(np.float32).eps],(unique[:-1]+unique[1:])/2,[unique[-1]]))
    for threshold in labelled_thresholds:
        f2=float(fbeta_score(validation_labels,np.asarray(validation_scores)>threshold,beta=2,zero_division=0))
        candidates.append((f2,None,float(threshold)))
    best=max(candidates,key=lambda x:(x[0],x[2]))
    return best[2],best[1],[{'f2':f,'percentile':p,'threshold':t,
                           'source':'normal_percentile' if p is not None else 'labelled_development'} for f,p,t in candidates]


def trial_configs(name,advanced=False):
    if name=='autoencoder':
        return [{'image_size':128,'epochs':30,'learning_rate':.001},
                {'image_size':128,'epochs':50,'learning_rate':.0003},
                {'image_size':256,'epochs':50,'learning_rate':.001}]
    if name=='padim':
        return [{'image_size':128,'n_features':50}, {'image_size':128,'n_features':100},
                {'image_size':256,'n_features':100}]
    return [{'image_size':128,'backbone':'resnet18','coreset_ratio':.02},
            {'image_size':256,'backbone':'resnet18','coreset_ratio':.01},
            {'image_size':128,'backbone':'wide_resnet50_2','coreset_ratio':.01},
            {'image_size':256,'backbone':'wide_resnet50_2','coreset_ratio':.005}]


def instantiate(name,category,parameters,device):
    extra={key:value for key,value in parameters.items() if key in ('backbone','coreset_ratio','n_features')}
    config=ExperimentConfig(image_size=parameters['image_size'],seed=42,epochs=parameters.get('epochs',1),
                            batch_size=4,learning_rate=parameters.get('learning_rate',.001),device=device)
    return model_class(name)(config,category,**extra)


def train_category(dataset,category,device):
    key=f'{dataset}/{category}'; base=DATA/dataset/category; destination=OUT/dataset/category
    destination.mkdir(parents=True,exist_ok=True)
    report_path=destination/'results.json'
    if report_path.exists():
        update(key,state='complete',report=str(report_path.relative_to(ROOT))); return
    update(key,state='auditing')
    split=prepare(base,dataset,category,destination)
    train=canonical_training(base,split['training'],DATA/'curated'/dataset/category)
    calibration=canonical_training(base,split['calibration'],DATA/'curated'/dataset/category)
    audit=split['audit']
    update(key,state='training',training_count=len(train),calibration_count=len(calibration),
           validation_count=len(split['development']),final_count=len(split['final_test']),audit=audit)
    names=('autoencoder','padim','patchcore') if dataset=='mvtec_ad' else ('patchcore',)
    chosen={}; trial_rows=[]
    split_hash=hashlib.sha256(json.dumps(split,sort_keys=True).encode()).hexdigest()
    for name in names:
        best=None; plateau=0
        for index,parameters in enumerate(trial_configs(name,dataset!='mvtec_ad')):
            trial_id=f'{name}_{index+1}'; trial_dir=destination/'trials'/trial_id
            trial_dir.mkdir(parents=True,exist_ok=True)
            record_path=trial_dir/'validation.json'; checkpoint=trial_dir/'model.pt'
            prior_dir=PRIOR/dataset/category/'trials'/trial_id
            if not checkpoint.exists() and (prior_dir/'model.pt').exists() and (prior_dir/'validation.json').exists():
                shutil.copy2(prior_dir/'model.pt',checkpoint)
                shutil.copy2(prior_dir/'validation.json',record_path)
            update(key,state='training',model=name,trial=trial_id,parameters=parameters)
            if record_path.exists() and checkpoint.exists():
                record=json.loads(record_path.read_text())
                if record.get('protocol_version')!='labelled_threshold_f2_v3':
                    model=model_class(name).load(checkpoint,device=device)
                    try:
                        normal_scores=[model.infer(read_rgb(p,model.config.image_size))[0] for p in calibration]
                        _,predictions=score_samples(model,base,split['development'])
                        threshold,percentile,threshold_trials=choose_threshold(normal_scores,
                            [i['label'] for i in split['development']],[p['anomaly_score'] for p in predictions])
                        model.threshold=threshold
                        model.provenance['validation_threshold_percentile']=percentile
                        model.provenance['threshold_selection']='labelled_development_F2'
                        validation,_=score_samples(model,base,split['development'])
                        model.save(checkpoint)
                        record.update(protocol_version='labelled_threshold_f2_v3',threshold=threshold,
                            selected_percentile=percentile,threshold_trials=threshold_trials,validation=validation)
                        record_path.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
                    finally:
                        del model; release()
            else:
                model=instantiate(name,category,parameters,device)
                try:
                    model.fit(train)
                    normal_scores=[model.infer(read_rgb(p,model.config.image_size))[0] for p in calibration]
                    model.threshold=calibrate(normal_scores,99)
                    # The final_test list is not read anywhere in this search loop.
                    validation,validation_predictions=score_samples(model,base,split['development'])
                    threshold,percentile,threshold_trials=choose_threshold(normal_scores,
                        [i['label'] for i in split['development']],
                        [r['anomaly_score'] for r in validation_predictions])
                    model.threshold=threshold
                    model.provenance={'dataset':dataset,'category':category,'split_sha256':split_hash,
                                      'training_regime':'all_clean_normals_except_held_out_calibration',
                                      'validation_threshold_percentile':percentile,'parameters':parameters,
                                      'threshold_selection':'labelled_development_F2'}
                    validation,_=score_samples(model,base,split['development'])
                    model.save(checkpoint)
                    record={'protocol_version':'labelled_threshold_f2_v3','model':name,'trial':trial_id,'parameters':parameters,'threshold':threshold,
                            'selected_percentile':percentile,'threshold_trials':threshold_trials,
                            'validation':validation,'checkpoint':str(checkpoint.relative_to(ROOT))}
                    record_path.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
                finally:
                    del model; release()
            trial_rows.append(record)
            rank=(record['validation']['f2'],record['validation']['image_auroc'] or 0,
                  record['validation']['pixel_auroc'] or 0)
            if best is None or rank>best[0]:
                best=(rank,record); plateau=0
            else:
                plateau+=1
            update(key,state='training',completed_trial=trial_id,validation=record['validation'])
            # All initial three candidates run; fourth PatchCore candidate only if still improving.
            if index>=2 and plateau>=2: break
        chosen[name]=best[1]
    winner=max(chosen,key=lambda name:(chosen[name]['validation']['f2'],
               chosen[name]['validation']['image_auroc'] or 0,chosen[name]['validation']['pixel_auroc'] or 0))
    update(key,state='final_evaluation',selected_model=winner)
    final_rows=[]
    for name,selection in chosen.items():
        checkpoint=ROOT/selection['checkpoint']; model=model_class(name).load(checkpoint,device=device)
        metrics,predictions=score_samples(model,base,split['final_test'],save=destination/'final'/name)
        for row in predictions: row['dataset']=dataset
        final_rows.append({'dataset':dataset,'category':category,'model':name,'selected_for_deployment':name==winner,
                           'training_images':len(train),'calibration_images':len(calibration),
                           'test_images':len(split['final_test']),'parameters':selection['parameters'],
                           'threshold':model.threshold,**metrics})
        (destination/'final'/name).mkdir(parents=True,exist_ok=True)
        (destination/'final'/name/'predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False)+'\n')
        del model; release()
    report={'dataset':dataset,'category':category,'protocol':split['protocol'],'split_sha256':split_hash,
            'selected_model':winner,'selection_rule':'development F2, then image AUROC, then pixel AUROC; no final-test selection',
            'search_scope':'finite recorded parameter grid; stop after two non-improving trials after initial three; no global-optimum claim',
            'selection_beta':2,'prior_final_test_exposure':(PRIOR/dataset/category/'results.json').exists(),
            'hardware':{'device':device,'torch':torch.__version__},'audit':audit,'trials':trial_rows,'final_results':final_rows}
    report_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    aggregate()
    update(key,state='complete',report=str(report_path.relative_to(ROOT)),selected_model=winner,final_results=final_rows)


def aggregate():
    reports=[json.loads(path.read_text()) for path in sorted(OUT.glob('*/*/results.json'))]
    rows=[r for report in reports for r in report['final_results']]
    write_csv(OUT/'final_metrics.csv',rows,['dataset','category','model','selected_for_deployment','training_images',
        'calibration_images','test_images','accuracy','balanced_accuracy','image_auroc','pixel_auroc','average_precision',
        'f2','f1','precision','recall','false_accept_rate','false_reject_rate','latency_ms','threshold','parameters','confusion_matrix'])
    (OUT/'final_results.json').write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--device',default='mps' if torch.backends.mps.is_available() else 'cpu')
    parser.add_argument('--category'); parser.add_argument('--once',action='store_true'); args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'status.json').exists(): STATUS.update(json.loads((OUT/'status.json').read_text()))
    torch.set_num_threads(4)
    items=[item for item in json.loads((ROOT/'experiments/datasets.json').read_text()) if item['dataset']!='d2s']
    if args.category: items=[item for item in items if item['category']==args.category]
    while True:
        outstanding=False
        for item in items:
            key=item['dataset']+'/'+item['category']
            if STATUS.get(key,{}).get('state') in ('complete','failed'): continue
            marker=DATA/item['dataset']/f".{item['category']}_extracted.json"
            if not marker.exists():
                outstanding=True; continue
            try:
                with (OUT.parent/'accelerator.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    train_category(item['dataset'],item['category'],args.device)
            except Exception as error:
                update(key,state='failed',error=str(error)); traceback.print_exc()
                # Do not automatically rerun a failed trial forever.
        if args.once or not outstanding: break
        time.sleep(30)
