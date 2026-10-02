"""D2S segmentation search using public train/validation annotations only.

Half the official public validation split selects models; the other half is an
untouched local final holdout. Official test labels are private; no test metrics
are invented. Generated YOLO labels are audited against original COCO masks.
"""
import argparse
import fcntl
import hashlib
import json
import random
import time
import traceback
from collections import defaultdict
from pathlib import Path
import cv2
import numpy as np
import torch
from PIL import Image
import yaml
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
from pycocotools import mask as mask_utils
from ultralytics import YOLO
from ultralytics.models.yolo.segment.train import SegmentationTrainer
from ultralytics.data.converter import merge_multi_segment

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/d2s'
PREPARED=ROOT/'data/d2s_yolo'
OUTPUT=ROOT/'outputs/d2s'
IMAGE_INDEX=None
STATUS={}


def status(**fields):
    STATUS.update(fields)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    temporary=OUTPUT/'status.tmp'
    temporary.write_text(json.dumps(STATUS,indent=2,allow_nan=False)+'\n')
    temporary.replace(OUTPUT/'status.json')
    print(fields,flush=True)


class F2SegmentationTrainer(SegmentationTrainer):
    """Checkpoint selection and early stopping use validation mask F2."""
    def validate(self):
        metrics=self.validator(self)
        segmentation=self.validator.metrics.seg
        precision=np.asarray(segmentation.p_curve)
        recall=np.asarray(segmentation.r_curve)
        if precision.size and recall.size:
            curve=5*precision*recall/np.maximum(1e-12,4*precision+recall)
            fitness=float(np.max(curve.mean(axis=0)))
        else:
            fitness=0.0
        metrics.pop('fitness',None)
        metrics['metrics/F2(M)']=fitness
        if self.best_fitness is None or fitness>self.best_fitness:
            self.best_fitness=fitness
        return metrics,fitness


def source_image(name):
    global IMAGE_INDEX
    if IMAGE_INDEX is None:
        IMAGE_INDEX=defaultdict(list)
        for p in BASE.rglob('*'):
            if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png'):
                IMAGE_INDEX[p.name].append(p)
    matches=IMAGE_INDEX[Path(name).name]
    if len(matches)!=1: raise ValueError(f'Cannot uniquely resolve D2S image: {name}')
    return matches[0]


def convert():
    manifest=PREPARED/'audit.json'
    if manifest.exists(): return json.loads(manifest.read_text())
    jsons=list(BASE.rglob('*.json'))
    train_candidates=[p for p in jsons if p.name=='D2S_training.json']
    val_candidates=[p for p in jsons if p.name=='D2S_validation.json']
    if len(train_candidates)!=1 or len(val_candidates)!=1:
        raise ValueError(f'Need unambiguous official D2S train/validation COCO JSONs: {jsons}')
    train=COCO(str(train_candidates[0])); val=COCO(str(val_candidates[0]))
    categories=sorted(train.cats); mapping={category:index for index,category in enumerate(categories)}
    val_ids=sorted(val.imgs); random.Random(42).shuffle(val_ids)
    midpoint=len(val_ids)//2
    development=set(val_ids[:midpoint]); final=set(val_ids[midpoint:])
    # Public official validation is partitioned by image ID; train stays official.
    groups=[('train',train,sorted(train.imgs)),('val',val,sorted(development)),('test',val,sorted(final))]
    PREPARED.mkdir(parents=True,exist_ok=True)
    audit={'train_annotation':str(train_candidates[0].relative_to(ROOT)),
           'val_annotation':str(val_candidates[0].relative_to(ROOT)),
           'split':{'development_validation_ids':sorted(development),'final_validation_ids':sorted(final)},
           'class_mapping':mapping,'counts':{},'empty_images':[],'polygon_iou':{},'image_hashes':{}}
    seen={}; ious=[]
    for split,coco,ids in groups:
        image_dir=PREPARED/'images'/split; label_dir=PREPARED/'labels'/split
        image_dir.mkdir(parents=True,exist_ok=True); label_dir.mkdir(parents=True,exist_ok=True)
        for image_id in ids:
            info=coco.imgs[image_id]; source=source_image(info['file_name'])
            with Image.open(source) as image:
                image.load()
                if image.size!=(info['width'],info['height']): raise ValueError('COCO/image size mismatch')
                decoded=np.asarray(image.convert('RGB')); digest=hashlib.sha256(decoded.tobytes()).hexdigest()
            if digest in seen and seen[digest]!=split: raise ValueError('Duplicate image leaks across D2S splits')
            seen[digest]=split; audit['image_hashes'][str(image_id)]=digest
            destination=image_dir/f'{image_id:06d}{source.suffix.lower()}'
            if not destination.exists(): destination.hardlink_to(source)
            annotations=coco.loadAnns(coco.getAnnIds(imgIds=image_id)); rows=[]
            if not annotations: audit['empty_images'].append(image_id)
            for annotation in annotations:
                mask=coco.annToMask(annotation).astype(np.uint8)
                contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                segments=[contour.reshape(-1,2) for contour in contours if len(contour)>=3]
                if not segments: raise ValueError(f'Empty/malformed object mask: {annotation["id"]}')
                polygon=segments[0] if len(segments)==1 else np.concatenate(merge_multi_segment([s.ravel().tolist() for s in segments]))
                # COCO decoding uses Fortran layout; OpenCV drawing needs a
                # contiguous row-major destination.
                restored=np.zeros(mask.shape,dtype=np.uint8)
                cv2.fillPoly(restored,[np.ascontiguousarray(np.rint(polygon),dtype=np.int32)],1)
                iou=float(((mask>0)&(restored>0)).sum()/max(1,((mask>0)|(restored>0)).sum()));ious.append(iou)
                # YOLO polygons cannot encode holes; quantify approximation loss.
                # Final evaluation below uses original COCO RLE ground truth.
                if iou<.5: raise ValueError(f'Severe polygon geometry loss (IoU={iou}): {annotation["id"]}')
                normalized=polygon/np.array([info['width'],info['height']])
                if not np.isfinite(normalized).all() or (normalized<0).any() or (normalized>1).any():
                    raise ValueError('Invalid polygon geometry')
                rows.append(str(mapping[annotation['category_id']])+' '+' '.join(f'{v:.8f}' for v in normalized.ravel()))
            (label_dir/f'{image_id:06d}.txt').write_text('\n'.join(rows)+'\n')
        audit['counts'][split]=len(ids)
    audit['polygon_iou']={'minimum':min(ious),'mean':float(np.mean(ious))}
    config={'path':str(PREPARED),'train':'images/train','val':'images/val','test':'images/test',
            'names':{mapping[k]:train.cats[k]['name'] for k in categories}}
    (PREPARED/'dataset.yaml').write_text(yaml.safe_dump(config,sort_keys=False))
    manifest.write_text(json.dumps(audit,indent=2)+'\n')
    return audit


def evaluate_original_coco(model,audit,device,split="final",confidence=.25):
    coco=COCO(str(ROOT/audit['val_annotation']))
    ids=audit['split']['development_validation_ids' if split=='development' else 'final_validation_ids']
    reverse={int(v):int(k) for k,v in audit['class_mapping'].items()}
    detections=[]
    thresholds=[.05,.1,.15,.2,.25,.35,.5] if split=='development' else [confidence]
    counts={threshold:[0,0,0] for threshold in thresholds}
    for image_id in ids:
        source=source_image(coco.imgs[image_id]['file_name'])
        prediction=model.predict(str(source),device=device,conf=.001,imgsz=640,retina_masks=True,verbose=False)[0]
        ground_truth=coco.loadAnns(coco.getAnnIds(imgIds=image_id))
        gt_rles=[coco.annToRLE(ann) for ann in ground_truth]
        local=[]
        if prediction.masks is not None:
            masks=prediction.masks.data.cpu().numpy()>.5
            for index in np.argsort(-prediction.boxes.conf.cpu().numpy()):
                mask=masks[index];category=reverse[int(prediction.boxes.cls[index].cpu())]
                score=float(prediction.boxes.conf[index].cpu())
                rle=mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
                rle['counts']=rle['counts'].decode('ascii')
                detections.append({'image_id':image_id,'category_id':category,'segmentation':rle,'score':score})
                local.append({'rle':rle,'category':category,'score':score})
        ious=mask_utils.iou([p['rle'] for p in local],gt_rles,[0]*len(gt_rles)) if local and gt_rles else np.zeros((len(local),len(gt_rles)))
        for threshold in thresholds:
            matched=set();tp=fp=0
            for index,predicted in enumerate(local):
                if predicted['score']<threshold:continue
                candidates=[(float(ious[index,j]),j) for j,annotation in enumerate(ground_truth)
                            if j not in matched and annotation['category_id']==predicted['category']]
                if candidates and max(candidates)[0]>=.5:
                    matched.add(max(candidates)[1]);tp+=1
                else:fp+=1
            counts[threshold][0]+=tp;counts[threshold][1]+=fp;counts[threshold][2]+=len(ground_truth)-len(matched)
    (OUTPUT/f'{split}_coco_predictions.json').write_text(json.dumps(detections)+'\n')
    if detections:
        evaluator=COCOeval(coco,coco.loadRes(detections),'segm');evaluator.params.imgIds=ids
        evaluator.evaluate();evaluator.accumulate();evaluator.summarize()
        average_precision={'mask_map50_95':float(evaluator.stats[0]),'mask_map50':float(evaluator.stats[1]),
                           'mask_map75':float(evaluator.stats[2])}
    else:average_precision={'mask_map50_95':0.0,'mask_map50':0.0,'mask_map75':0.0}
    choices=[]
    for threshold,(tp,fp,fn) in counts.items():
        precision=tp/max(1,tp+fp);recall=tp/max(1,tp+fn)
        choices.append({'confidence':threshold,'tp':tp,'fp':fp,'fn':fn,'mask_precision':precision,
                        'mask_recall':recall,'mask_f1':2*precision*recall/max(1e-12,precision+recall),
                        'mask_f2':5*precision*recall/max(1e-12,4*precision+recall)})
    selected=max(choices,key=lambda x:(x['mask_f2'],x['confidence']))
    return {**average_precision,**selected,'confidence_trials':choices,'match_iou':.5,
            'ground_truth':'original COCO RLE masks; no polygon approximation in final metrics'}


def main():
    torch.set_num_threads(4)
    parser=argparse.ArgumentParser();parser.add_argument('--device',default='mps');parser.add_argument('--wait',action='store_true')
    parser.add_argument('--after-anomaly-suite',action='store_true');args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if (OUTPUT/'results.json').exists():
        status(state='complete',phase='final_report',report='outputs/d2s/results.json')
        return
    status(state='running',phase='waiting_for_downloads',selection_metric='mask F2')
    while not ((BASE/'.images_extracted.json').exists() and (BASE/'.annotations_extracted.json').exists()):
        if not args.wait: raise FileNotFoundError('D2S downloads not ready')
        time.sleep(30)
    # CPU-only preparation can finish while the anomaly worker owns MPS.
    status(phase='auditing_and_converting')
    audit=convert()
    if args.after_anomaly_suite:
        status(phase='waiting_for_anomaly_suite')
        while True:
            path=ROOT/'outputs/experiment_status.json'
            suite=json.loads(path.read_text()) if path.exists() else {}
            if suite.get('state')=='failed':
                raise RuntimeError('Anomaly suite failed: '+suite.get('error','unknown error'))
            if suite.get('phase')=='waiting_for_d2s_final_report':break
            time.sleep(30)
    with (ROOT/'outputs/accelerator.lock').open('a') as lock:
        status(phase='waiting_for_accelerator')
        fcntl.flock(lock,fcntl.LOCK_EX)
        trials=[]
        candidates=[{'weights':'yolov8n-seg.pt','imgsz':640,'lr0':.001,'epochs':60},
                    {'weights':'yolov8n-seg.pt','imgsz':640,'lr0':.0003,'epochs':80},
                    {'weights':'yolov8s-seg.pt','imgsz':640,'lr0':.001,'epochs':60}]
        best=None;plateau=0
        for index,params in enumerate(candidates):
            name=f'trial_{index+1}';record=OUTPUT/name/'validation.json';record.parent.mkdir(parents=True,exist_ok=True)
            status(phase='training',trial=name,parameters=params)
            if record.exists(): result=json.loads(record.read_text())
            else:
                model=YOLO(params['weights'])
                model.train(trainer=F2SegmentationTrainer,data=str(PREPARED/'dataset.yaml'),device=args.device,batch=4,workers=0,
                            project=str(OUTPUT),name=name,exist_ok=True,seed=42,deterministic=True,
                            patience=12,optimizer='AdamW',cos_lr=True,close_mosaic=10,
                            hsv_h=.015,hsv_s=.3,hsv_v=.2,degrees=10,translate=.1,scale=.3,
                            fliplr=.5,flipud=0,mosaic=.5,mixup=0,copy_paste=.1,
                            **{key:value for key,value in params.items() if key!='weights'})
                metrics=YOLO(str(OUTPUT/name/'weights/best.pt')).val(data=str(PREPARED/'dataset.yaml'),split='val',device=args.device,batch=4,workers=0)
                status(phase='development_evaluation',trial=name)
                original_validation=evaluate_original_coco(YOLO(str(OUTPUT/name/'weights/best.pt')),audit,args.device,split='development')
                result={'parameters':params,'validation':metrics.results_dict,'original_validation':original_validation,'checkpoint':str((OUTPUT/name/'weights/best.pt').relative_to(ROOT))}
                record.write_text(json.dumps(result,indent=2)+'\n')
            trials.append(result);rank=result['original_validation']['mask_f2']
            status(completed_trial=name,development_f2=rank)
            if best is None or rank>best[0]: best=(rank,result);plateau=0
            else: plateau+=1
            if plateau>=2:break
        # Final held-out half of public validation evaluated exactly once after selection.
        selected=best[1];model=YOLO(str(ROOT/selected['checkpoint']))
        status(phase='final_evaluation',selected=selected['checkpoint'])
        final=model.val(data=str(PREPARED/'dataset.yaml'),split='test',device=args.device,batch=4,workers=0,
                        project=str(OUTPUT),name='final',save_json=True)
        original_metrics=evaluate_original_coco(model,audit,args.device,confidence=selected['original_validation']['confidence'])
        report={'dataset':'d2s','task':'instance_segmentation','protocol':'official train; half public validation for selection; half held out for final evaluation',
                'official_private_test_metrics':None,'private_test_reason':'Official test annotations are not public',
                'selection':'development object-level mask F2 at IoU 0.5; confidence also selected on development','audit':audit,'trials':trials,'selected':selected,
                'final_metrics':original_metrics,'polygon_label_metrics':final.results_dict,
                'accuracy':None,'accuracy_reason':'Classification accuracy is not an instance segmentation metric'}
        (OUTPUT/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        status(state='complete',phase='final_report',report='outputs/d2s/results.json')
        print(json.dumps(report['final_metrics'],indent=2),flush=True)

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        status(state='failed',error=str(error),traceback=traceback.format_exc())
        raise
