"""F2 selection and real-data protocol mechanics; fixtures are not results."""
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from app.services.ml.shared.metrics import evaluate

EXPERIMENTS=Path(__file__).resolve().parents[2]/'experiments'
sys.path.insert(0,str(EXPERIMENTS))
from data_protocol import prepare,canonical_training


def test_f2_weights_false_negatives_more():
    metrics=evaluate([1,1,1,1,1,0],[.9,.9,.1,.1,.1,.9],.5,[1]*6)
    assert metrics['f1']==pytest.approx(.5)
    assert metrics['f2']==pytest.approx(10/23)
    assert metrics['confusion_matrix']==[[0,1],[3,2]]


def test_frozen_protocol_audit_and_splits(tmp_path):
    base=tmp_path/'screw';good=base/'train/good';good.mkdir(parents=True)
    for i in range(60):Image.new('RGB',(16,16),(i,0,0)).save(good/f'{i}.png')
    # Preserve original files; duplicate normal is removed only from fitting view.
    Image.new('RGB',(16,16),(0,0,0)).save(good/'duplicate.png')
    for defect in ('good','scratch'):
        directory=base/'test'/defect;directory.mkdir(parents=True)
        for i in range(10):
            Image.new('RGB',(16,16),(i,80,120 if defect=='good' else 180)).save(directory/f'{i}.png')
            if defect!='good':
                mask=base/'ground_truth'/defect;mask.mkdir(parents=True,exist_ok=True)
                Image.new('L',(16,16),255).save(mask/f'{i}_mask.png')
    result=prepare(base,'mvtec_ad','screw',tmp_path/'out')
    assert len(result['training'])==40 and len(result['calibration'])==20
    assert len(result['development'])==4 and len(result['final_test'])==16
    assert len(result['audit']['duplicate_training'])==1
    assert not {i['sha256'] for i in result['development']} & {i['sha256'] for i in result['final_test']}
    assert prepare(base,'mvtec_ad','screw',tmp_path/'out')==result
    paths=canonical_training(base,result['training'],tmp_path/'view')
    assert len(paths)==40 and all(p.parent.name=='good' for p in paths)


def test_threshold_search_uses_f2():
    pytest.importorskip('torch')
    from train_suite import choose_threshold
    threshold,_,trials=choose_threshold([.15,.2,.25],[1,1,1,1,0,0],[.12,.21,.22,.8,.13,.1])
    assert any(t['source']=='labelled_development' for t in trials)
    assert all('f2' in t for t in trials)
    metrics=evaluate([1,1,1,1,0,0],[.12,.21,.22,.8,.13,.1],threshold,[1]*6)
    assert metrics['recall']==1


def test_segmentation_epoch_fitness_uses_f2():
    pytest.importorskip('ultralytics')
    from types import SimpleNamespace
    from train_d2s import F2SegmentationTrainer
    class Validator:
        metrics=SimpleNamespace(seg=SimpleNamespace(p_curve=np.array([[.5,.9]]),r_curve=np.array([[1,.5]])))
        def __call__(self,trainer):return {'fitness':.99}
    trainer=F2SegmentationTrainer.__new__(F2SegmentationTrainer)
    trainer.validator=Validator();trainer.best_fitness=None
    metrics,fitness=trainer.validate()
    assert fitness==pytest.approx(5/6)
    assert trainer.best_fitness==fitness and metrics['metrics/F2(M)']==fitness


def test_final_report_distinguishes_category_macro_from_pooled_f2(tmp_path,monkeypatch):
    import json
    import finish_training
    output=tmp_path/'outputs'
    (output/'training_f2').mkdir(parents=True)
    (output/'30shot_f2').mkdir()
    (output/'d2s').mkdir()
    (tmp_path/'data').mkdir()
    reports=[]
    for category,confusion,f2 in [('first',[[2,1],[0,3]],15/16),('second',[[1,1],[2,0]],0)]:
        row={key:0.0 for key in ('accuracy','balanced_accuracy','f1','precision','recall','image_auroc',
                               'pixel_auroc','average_precision','false_accept_rate','false_reject_rate','latency_ms')}
        row.update(dataset='fixture',category=category,model='fixture',selected_for_deployment=True,
                   training_images=30,test_images=sum(map(sum,confusion)),parameters={},confusion_matrix=confusion,f2=f2)
        reports.append({'final_results':[row]})
    (output/'training_f2/final_results.json').write_text(json.dumps(reports))
    (output/'30shot_f2/results.json').write_text('[]')
    (output/'d2s/results.json').write_text('{"final_metrics": {}}')
    (tmp_path/'data/download_status.json').write_text('{}')
    monkeypatch.setattr(finish_training,'ROOT',tmp_path)
    monkeypatch.setattr(finish_training,'OUT',output)
    finish_training.report()
    report=json.loads((output/'FINAL_RESULTS.json').read_text())
    assert report['anomaly_category_macro_metrics']['f2']==pytest.approx(15/32)
    assert report['anomaly_pooled_decision_metrics']['f2']==pytest.approx(.6)
    assert report['anomaly_pooled_decision_metrics']['confusion_matrix']==[[3,2],[2,3]]


def test_d2s_conversion_accepts_fortran_coco_masks(tmp_path, monkeypatch):
    pytest.importorskip('ultralytics')
    import json
    from pycocotools import mask as mask_utils
    import train_d2s
    base=tmp_path/'data/d2s';base.mkdir(parents=True)
    prepared=tmp_path/'prepared'
    mask=np.zeros((8,8),dtype=np.uint8);mask[2:6,2:6]=1
    rle=mask_utils.encode(np.asfortranarray(mask));rle['counts']=rle['counts'].decode('ascii')
    assert mask_utils.decode(rle).flags.f_contiguous
    for split,ids in [('training',[1]),('validation',[2,3])]:
        images=[];annotations=[]
        for image_id in ids:
            name=f'{image_id}.png';Image.new('RGB',(8,8),(image_id*30,0,0)).save(base/name)
            images.append({'id':image_id,'file_name':name,'width':8,'height':8})
            annotations.append({'id':image_id,'image_id':image_id,'category_id':1,
                                'segmentation':rle,'area':16,'bbox':[2,2,4,4],'iscrowd':0})
        (base/f'D2S_{split}.json').write_text(json.dumps({'images':images,'annotations':annotations,
                                          'categories':[{'id':1,'name':'fixture'}]}))
    monkeypatch.setattr(train_d2s,'ROOT',tmp_path)
    monkeypatch.setattr(train_d2s,'BASE',base)
    monkeypatch.setattr(train_d2s,'PREPARED',prepared)
    monkeypatch.setattr(train_d2s,'IMAGE_INDEX',None)
    audit=train_d2s.convert()
    assert audit['counts']=={'train':1,'val':1,'test':1}
    assert audit['polygon_iou']['minimum']==1
    assert len(list((prepared/'labels').rglob('*.txt')))==3


@pytest.mark.parametrize('state',['running','complete'])
def test_publish_report_rejects_unfinished_artifacts(tmp_path,monkeypatch,state):
    import json
    import publish_results
    (tmp_path/'outputs/30shot_f2').mkdir(parents=True)
    (tmp_path/'models').mkdir()
    (tmp_path/'outputs/experiment_status.json').write_text(json.dumps({'state':state}))
    (tmp_path/'outputs/30shot_f2/results.json').write_text('[]')
    (tmp_path/'models/catalog.json').write_text('{}')
    monkeypatch.setattr(publish_results,'ROOT',tmp_path)
    with pytest.raises(RuntimeError):publish_results.build(require_complete=True)
    assert not (tmp_path/'docs/results/metrics.json').exists()
