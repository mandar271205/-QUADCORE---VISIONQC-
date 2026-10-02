"""Fixtures exercise mechanics only; they are never reported as MVTec metrics."""
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from app.services.ml.shared.data import create_manifest, load_manifest, validate_good
from app.services.ml.shared.metrics import evaluate
from app.services.ml.shared.result import Prediction, calibrate, normalize_score


def test_manifest_reuse_hashes_and_no_leakage(tmp_path):
    folder = tmp_path / 'screw/train/good'
    folder.mkdir(parents=True)
    for i in range(34):
        Image.new('RGB', (16, 16), (i, 50, 80)).save(folder / f'{i:03}.png')
    manifest = tmp_path / 'subset.json'
    create_manifest(tmp_path, 'screw', manifest, calibration_count=4)
    doc, train, calibration = load_manifest(tmp_path, manifest)
    assert len(train) == 30 and len(calibration) == 4 and not set(train) & set(calibration)
    other = tmp_path / 'other.json'
    create_manifest(tmp_path, 'screw', other, calibration_count=4)
    assert manifest.read_bytes() == other.read_bytes()
    with pytest.raises(FileExistsError):
        create_manifest(tmp_path, 'screw', manifest)
    doc['calibration'][0] = doc['train'][0]
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='held out'):
        load_manifest(tmp_path, manifest)
    with pytest.raises(ValueError):
        validate_good([tmp_path / 'screw/test/good/000.png'])


def test_manifest_rejects_changed_file_and_traversal(tmp_path):
    folder = tmp_path / 'cable/train/good'; folder.mkdir(parents=True)
    for i in range(31):
        Image.new('RGB', (16, 16), (i, 0, 0)).save(folder / f'{i}.png')
    path = tmp_path / 'subset.json'
    create_manifest(tmp_path, 'cable', path, calibration_count=1)
    doc, train, _ = load_manifest(tmp_path, path)
    train[0].write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        load_manifest(tmp_path, path)
    doc['train'][0] = '../../outside.png'; path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='only reference'):
        load_manifest(tmp_path, path)


def test_metrics_known_confusion_matrix_and_pixels():
    result = evaluate([0,0,1,1], [.1,.8,.2,.9], .5, [1,2,3,4],
                      [np.array([[0,1]])]*4, [np.array([[.1,.9]])]*4)
    assert result['image_auroc'] == .75
    assert result['pixel_auroc'] == 1
    assert result['f1'] == result['precision'] == result['recall'] == .5
    assert result['false_accept_rate'] == result['false_reject_rate'] == .5
    assert result['latency_ms'] == 2.5


def test_undefined_metrics_are_explicit():
    result = evaluate([0], [.1], .5, [1])
    assert result['image_auroc'] is None and result['false_accept_rate'] is None
    assert 'pixel_auroc' in result['unavailable']
    with pytest.raises(ValueError):
        evaluate([0,1], [float('nan'),1], .5, [1,1])


def test_threshold_and_prediction_contract():
    threshold = calibrate([1,2,3], 99)
    assert threshold == pytest.approx(2.98)
    assert normalize_score(threshold, threshold) == .5
    result = Prediction('mvtec_ad', 'screw', 'padim', threshold, threshold, None, .1)
    assert result.to_dict()['verdict'] == 'PASS'
    result.anomaly_score += 1
    assert result.verdict == 'FAIL'
    for scores in ([], [float('inf')], [-1]):
        with pytest.raises(ValueError):
            calibrate(scores)
    with pytest.raises(ValueError):
        Prediction('mvtec_ad', 'screw', 'padim', float('nan'), 1, None, 1)
