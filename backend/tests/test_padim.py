"""PaDiM distribution/checkpoint mechanics; fixtures are not benchmark evidence."""
import numpy as np
import pytest
from PIL import Image
from app.services.ml.shared.config import ExperimentConfig


def test_padim_saved_distribution(tmp_path):
    pytest.importorskip('anomalib')
    from app.services.ml.padim import PadimBaseline
    folder = tmp_path / 'train/good'; folder.mkdir(parents=True)
    rng = np.random.default_rng(7); paths = []
    for i in range(4):
        path = folder / f'{i}.png'
        Image.fromarray(rng.integers(0,256,(32,32,3),dtype=np.uint8)).save(path)
        paths.append(path)
    # Unit tests avoid network; the separately executed smoke used pretrained=True.
    model = PadimBaseline(ExperimentConfig(image_size=32,batch_size=2),'transistor',
                          initialize_pretrained=False)
    model.fit(paths[:3]); model.calibrate(paths[3:]); model.save(tmp_path/'padim.pt')
    restored = PadimBaseline.load(tmp_path/'padim.pt')
    expected, a = model.predict(paths[0])
    actual, b = restored.predict(paths[0],tmp_path/'map.png')
    assert actual.anomaly_score == pytest.approx(expected.anomaly_score, rel=1e-3, abs=1e-4)
    assert np.allclose(a,b,rtol=1e-3,atol=1e-4)
    assert (tmp_path/'map.png').is_file()
    assert restored.model.memory_bank == []
    assert restored.model.gaussian.mean.numel() > 0
