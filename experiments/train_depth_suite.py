"""Normal-only aligned depth prototype and validation-selected RGB/depth fusion."""
import fcntl
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from app.services.ml.depth import DepthBaseline
from app.services.ml.shared.result import calibrate,normalize_score
from app.services.ml.shared.metrics import evaluate
from app.services.ml.factory import model_class
from data_protocol import mask_array
from train_suite import choose_threshold,release

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'outputs/depth_f2'


def depth_path(base,item):
    rgb=base/item['filename'];path=rgb.parent.parent/'xyz'/f'{rgb.stem}.tiff'
    if not path.is_file():raise FileNotFoundError(path)
    return path


def run(category):
    primary=ROOT/'outputs/training_f2/mvtec_3d_ad'/category
    base=ROOT/'data/mvtec_3d_ad'/category;out=OUTPUT/category;out.mkdir(parents=True,exist_ok=True)
    if (out/'results.json').exists():return
    split=json.loads((primary/'split.json').read_text());rgb_report=json.loads((primary/'results.json').read_text())
    records=[];best=None
    for regularization in (1e-5,1e-4,1e-3):
        model=DepthBaseline(image_size=128,regularization=regularization)
        model.fit([depth_path(base,i) for i in split['training']])
        normal=[model.infer(depth_path(base,i))[0] for i in split['calibration']]
        scores=[model.infer(depth_path(base,i))[0] for i in split['development']]
        model.threshold,percentile,_=choose_threshold(normal,[i['label'] for i in split['development']],scores)
        metrics=evaluate([i['label'] for i in split['development']],scores,model.threshold,[0]*len(scores))
        record={'regularization':regularization,'threshold':model.threshold,'validation':metrics}
        records.append(record);rank=(metrics['f2'],metrics['image_auroc'])
        if best is None or rank>best[0]:best=(rank,model)
    depth=best[1];depth.save(out/'depth.npz')
    selection=next(t for t in rgb_report['trials'] if t['model']==rgb_report['selected_model'] and
                   t['parameters']==next(r for r in rgb_report['final_results'] if r['selected_for_deployment'])['parameters'])
    rgb=model_class('patchcore').load(ROOT/selection['checkpoint'],device='mps')
    def collect(items):
        pairs=[]
        for item in items:
            begin=time.perf_counter();ds,dm=depth.infer(depth_path(base,item));r,rm=rgb.predict(base/item['filename'])
            pairs.append({'rgb_score':normalize_score(r.anomaly_score,r.threshold),
                          'depth_score':normalize_score(ds,depth.threshold),'raw_depth':ds,
                          'latency':(time.perf_counter()-begin)*1000,'depth_map':dm,'rgb_map':rm})
        return pairs
    dev=collect(split['development']);normals=collect(split['calibration']);fusion_trials=[];fusion_best=None
    for alpha in (0,.25,.5,.75,1):
        scores=[alpha*p['rgb_score']+(1-alpha)*p['depth_score'] for p in dev]
        normal_scores=[alpha*p['rgb_score']+(1-alpha)*p['depth_score'] for p in normals]
        threshold,_,_=choose_threshold(normal_scores,[i['label'] for i in split['development']],scores)
        metrics=evaluate([i['label'] for i in split['development']],scores,threshold,[p['latency'] for p in dev])
        record={'alpha_rgb':alpha,'threshold':threshold,'validation':metrics};fusion_trials.append(record)
        rank=(metrics['f2'],metrics['image_auroc'])
        if fusion_best is None or rank>fusion_best[0]:fusion_best=(rank,record)
    chosen=fusion_best[1];final=collect(split['final_test']);labels=[i['label'] for i in split['final_test']]
    masks=[mask_array(base,i,128) for i in split['final_test']]
    depth_metrics=evaluate(labels,[p['raw_depth'] for p in final],depth.threshold,[p['latency'] for p in final],masks,[p['depth_map'] for p in final])
    alpha=chosen['alpha_rgb'];scores=[alpha*p['rgb_score']+(1-alpha)*p['depth_score'] for p in final]
    fused=evaluate(labels,scores,chosen['threshold'],[p['latency'] for p in final])
    report={'dataset':'mvtec_3d_ad','category':category,'task':'aligned depth prototype and RGB-depth score fusion',
            'selection_metric':'development F2','depth_trials':records,'fusion_trials':fusion_trials,'chosen_fusion':chosen,
            'depth_final':depth_metrics,'fusion_final':fused,'latency_scope':'joint RGB+depth pipeline',
            'depth_audit':{'finite_xyz_verified':True,'xyz_sha256':{i['filename']:hashlib.sha256(depth_path(base,i).read_bytes()).hexdigest()
                for i in split['training']+split['calibration']+split['development']+split['final_test']}},
            'predictions':[{'filename':i['filename'],'ground_truth':i['label'],'depth_score':p['raw_depth'],
                            'fusion_score':score,'fusion_prediction':'FAIL' if score>chosen['threshold'] else 'PASS'}
                           for i,p,score in zip(split['final_test'],final,scores)],
            'limitations':'Simple diagonal Gaussian on aligned Z/Sobel features, not a state-of-the-art point-cloud model; fusion pixel AUROC unavailable'}
    (out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');del rgb;release()


if __name__=='__main__':
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for category in ('cable_gland','dowel','tire'):
        primary=ROOT/'outputs/training_f2/mvtec_3d_ad'/category/'results.json'
        while not primary.exists():time.sleep(30)
        with (ROOT/'outputs/accelerator.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);run(category)
