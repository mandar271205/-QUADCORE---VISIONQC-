"""Pairing and missing ROI handling with a PatchCore-shaped fixture double."""
import numpy as np
from PIL import Image
from app.services.ml.roi import OpenCVROIExtractor
from app.services.ml.roi_experiment import run_roi_experiment
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig


class PatchcoreFixture(Baseline):
    name = 'patchcore'
    def fit(self,paths):
        raise AssertionError('Inference ablation cannot fit')
    def infer(self,rgb):
        anomaly_map = rgb.mean(axis=2)
        return float(anomaly_map.mean()),anomaly_map,None
    def save(self,path):
        raise AssertionError('No fake checkpoint')
    @classmethod
    def load(cls,path,device='cpu'):
        raise AssertionError('Not used')


def test_roi_ablation_exports_and_no_detection(tmp_path):
    for label in ('good','scratch'):
        folder = tmp_path/'screw/test'/label; folder.mkdir(parents=True)
        pixels = np.zeros((80,100,3),dtype=np.uint8)
        pixels[20:60,30:70] = 255
        Image.fromarray(pixels).save(folder/'0.png')
    model=PatchcoreFixture(ExperimentConfig(image_size=16),'screw'); model.threshold=.5
    report=run_roi_experiment(tmp_path,'screw',model,OpenCVROIExtractor(),tmp_path/'out')
    assert report['mode']=='inference_only_ablation'
    assert report['roi_metrics'] is not None
    assert all(r['bbox']==[30,20,70,60] for r in report['predictions'])
    assert len(list((tmp_path/'out/examples').rglob('*_crop.png')))==2
    Image.new('RGB',(100,80)).save(tmp_path/'screw/test/good/0.png')
    report=run_roi_experiment(tmp_path,'screw',model,OpenCVROIExtractor(),tmp_path/'out')
    assert report['roi_metrics'] is None
    assert report['predictions'][0]['roi_score'] is None
    assert report['predictions'][0]['roi_prediction'] is None
