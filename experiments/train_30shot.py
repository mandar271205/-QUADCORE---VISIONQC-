"""Fixed 30-shot baseline comparison on the full-run frozen dev/final split."""
import hashlib
import json
import random
import time
import fcntl
from pathlib import Path
from data_protocol import prepare,canonical_training
from train_suite import choose_threshold,score_samples,release
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.preprocessing import read_rgb
from app.services.ml.shared.result import calibrate
from app.services.ml.factory import model_class
from app.services.ml.comparison import provenance,write_csv

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'outputs/30shot_f2'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);rows=[]
    for category in ('screw','cable','transistor'):
        base=ROOT/'data/mvtec_ad'/category;directory=OUTPUT/category;directory.mkdir(parents=True,exist_ok=True)
        full=ROOT/'outputs/training_f2/mvtec_ad'/category/'results.json'
        while not full.exists():time.sleep(30)
        report_path=directory/'results.json'
        if report_path.exists():rows.extend(json.loads(report_path.read_text())['results']);continue
        split=json.loads((full.parent/'split.json').read_text())
        pool=list(split['training']);random.Random(42).shuffle(pool);selected=pool[:30]
        # Calibration is the same held-out normal set used in all-normal fitting.
        manifest={'dataset':'mvtec_ad','category':category,'seed':42,'shots':30,
                  'train':[i['filename'] for i in selected],
                  'calibration':[i['filename'] for i in split['calibration']]}
        manifest['sha256']={name:hashlib.sha256((base/name).read_bytes()).hexdigest()
                            for name in manifest['train']+manifest['calibration']}
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        train=canonical_training(base,selected,ROOT/'data/curated_30shot'/category)
        calibration=canonical_training(base,split['calibration'],ROOT/'data/curated_30shot'/category)
        config=ExperimentConfig(image_size=256,epochs=50,batch_size=4,learning_rate=.001,device='mps')
        results=[]
        for name in ('autoencoder','padim','patchcore'):
            checkpoint=directory/name/'model.pt';checkpoint.parent.mkdir(parents=True,exist_ok=True)
            if checkpoint.exists():model=model_class(name).load(checkpoint,device=config.device)
            else:
                model=model_class(name)(config,category)
                model.fit(train)
                normals=[model.infer(read_rgb(p,config.image_size))[0] for p in calibration]
                model.threshold=calibrate(normals,99)
                _,predictions=score_samples(model,base,split['development'])
                model.threshold,percentile,_=choose_threshold(normals,[i['label'] for i in split['development']],
                                                              [r['anomaly_score'] for r in predictions])
                model.provenance=provenance(manifest,config)
                model.save(checkpoint)
            validation,_=score_samples(model,base,split['development'])
            final,predictions=score_samples(model,base,split['final_test'],save=directory/name)
            result={'dataset':'mvtec_ad','category':category,'model':name,'training_images':30,
                    'calibration_images':len(calibration),'test_images':len(split['final_test']),
                    'threshold':model.threshold,'validation':validation,**final}
            results.append(result);print(result,flush=True)
            (directory/name/'predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False)+'\n')
            del model;release()
        report={'dataset':'mvtec_ad','category':category,'shots':30,'shared_manifest':manifest,
                'preprocessing':{'image_size':256,'resize':'bilinear','color':'RGB','crop':None},
                'protocol':split['protocol'],'results':results}
        report_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');rows.extend(results)
        write_csv(OUTPUT/'comparison.csv',rows,['dataset','category','model','training_images','calibration_images',
                  'test_images','accuracy','balanced_accuracy','image_auroc','pixel_auroc','average_precision',
                  'f2','f1','precision','recall','false_accept_rate','false_reject_rate','latency_ms','threshold','confusion_matrix'])
        (OUTPUT/'results.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    with (ROOT/'outputs/accelerator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        main()
