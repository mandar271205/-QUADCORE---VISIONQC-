"""Training, held-out calibration, inference and checkpoint regression tests."""
import numpy as np
import pytest
from PIL import Image
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.preprocessing import read_rgb


def test_autoencoder_checkpoint_heatmaps_and_no_retraining(tmp_path):
    pytest.importorskip('torch')
    from app.services.ml.autoencoder.inference import AutoencoderBaseline
    good = tmp_path / 'train/good'; good.mkdir(parents=True)
    rng = np.random.default_rng(42)
    paths = []
    for i in range(4):
        path = good / f'{i}.png'
        Image.fromarray(rng.integers(0,256,(32,32,3),dtype=np.uint8)).save(path)
        paths.append(path)
    model = AutoencoderBaseline(ExperimentConfig(image_size=32,epochs=1,batch_size=2),'screw')
    with pytest.raises(RuntimeError):
        model.predict(paths[0])
    model.fit(paths[:3])
    with pytest.raises(ValueError, match='held out'):
        model.calibrate(paths[:1])
    model.calibrate(paths[3:]); model.save(tmp_path / 'model.pt')
    restored = AutoencoderBaseline.load(tmp_path / 'model.pt')
    before = {k:v.clone() for k,v in restored.model.state_dict().items()}
    original, a = model.predict(paths[0])
    prediction, b = restored.predict(paths[0],tmp_path/'map.png')
    assert original.anomaly_score == prediction.anomaly_score and np.allclose(a,b)
    assert a.shape == (32,32)
    assert (tmp_path/'map.png').is_file() and (tmp_path/'map_reconstruction.png').is_file()
    assert (tmp_path/'map.npy').is_file()
    assert all((before[k] == v).all() for k,v in restored.model.state_dict().items())
    with pytest.raises(ValueError):
        model.fit([tmp_path/'test/defect/0.png'])
