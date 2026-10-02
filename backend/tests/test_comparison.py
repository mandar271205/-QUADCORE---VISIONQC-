"""Test aggregation/provenance with a test double; no real metrics are asserted."""
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from app.services.ml.comparison import provenance, run_comparison, aggregate_reports
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.data import create_manifest, load_manifest


class FixtureBaseline(Baseline):
    name = 'autoencoder'
    def fit(self, paths):
        raise AssertionError('Comparison must never train')
    def infer(self, rgb):
        amap = rgb.mean(axis=2)
        return float(amap.mean()), amap, None
    def save(self, path):
        raise AssertionError('No checkpoints for fixture model')
    @classmethod
    def load(cls, path, device='cpu'):
        raise AssertionError('Not used')


def fixture_dataset(root):
    folder = root/'screw/train/good'; folder.mkdir(parents=True)
    for i in range(31):
        Image.new('RGB',(16,16),(i,0,0)).save(folder/f'{i}.png')
    for label in ('good','scratch'):
        folder = root/'screw/test'/label; folder.mkdir(parents=True)
        for i in range(6):
            Image.new('RGB',(16,16),(i*10,100,100)).save(folder/f'{i}.png')
    mask_folder = root/'screw/ground_truth/scratch'; mask_folder.mkdir(parents=True)
    for i in range(6):
        mask = np.zeros((16,16),dtype=np.uint8); mask[4:8,4:8] = 255
        Image.fromarray(mask).save(mask_folder/f'{i}_mask.png')
    manifest = root/'subset.json'
    create_manifest(root,'screw',manifest,calibration_count=1)
    return manifest


def test_comparison_exports_and_missing_patchcore(tmp_path):
    manifest = fixture_dataset(tmp_path)
    document, _, _ = load_manifest(tmp_path,manifest)
    config = ExperimentConfig(image_size=16,epochs=1)
    model = FixtureBaseline(config,'screw'); model.threshold = .2
    model.provenance = provenance(document,config)
    output = tmp_path/'out'
    report = run_comparison(tmp_path,manifest,{'autoencoder':model},output,config)
    aggregate_reports(output)
    assert len(report['examples']) == 10 and len(report['predictions']) == 12
    assert report['results'][2]['status'] == 'unavailable'
    assert report['results'][2]['image_auroc'] is None
    assert (output/'metrics/comparison.csv').exists()
    assert (output/'comparison/summary.json').exists()
    assert len(list((output/'comparison/examples').rglob('*.png'))) == 20
    model.provenance = {}
    with pytest.raises(ValueError, match='mismatch'):
        run_comparison(tmp_path,manifest,{'autoencoder':model},output,config)
