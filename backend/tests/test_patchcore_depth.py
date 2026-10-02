"""PatchCore and depth checkpoint mechanics using explicitly nonbenchmark fixtures."""
import numpy as np
import pytest
from PIL import Image
from app.services.ml.shared.config import ExperimentConfig


def test_patchcore_checkpoint(tmp_path):
    pytest.importorskip('anomalib')
    from app.services.ml.patchcore import PatchCoreBaseline
    folder=tmp_path/'train/good';folder.mkdir(parents=True);paths=[]
    for i in range(4):
        p=folder/f'{i}.png';Image.fromarray(np.random.default_rng(i).integers(0,256,(32,32,3),dtype=np.uint8)).save(p);paths.append(p)
    model=PatchCoreBaseline(ExperimentConfig(image_size=32,batch_size=2),'screw',coreset_ratio=.5,initialize_pretrained=False,max_training_patches=30)
    model.fit(paths[:3]);model.calibrate(paths[3:]);model.save(tmp_path/'model.pt')
    expected,a=model.predict(paths[0]);loaded=PatchCoreBaseline.load(tmp_path/'model.pt');actual,b=loaded.predict(paths[0])
    assert actual.anomaly_score==pytest.approx(expected.anomaly_score,rel=1e-3,abs=1e-4)
    assert np.allclose(a,b,rtol=1e-3,atol=1e-4)
    assert loaded.model.memory_bank.numel()>0
    assert loaded.max_training_patches==30
    assert len(loaded.model.memory_bank)<=15


def test_depth_checkpoint_detects_local_geometry(tmp_path):
    tifffile=pytest.importorskip('tifffile')
    from app.services.ml.depth import DepthBaseline
    folder=tmp_path/'train/good/xyz';folder.mkdir(parents=True);paths=[]
    for i in range(4):
        xyz=np.zeros((32,32,3),dtype=np.float32);xyz[4:28,4:28,2]=1+i*.001
        path=folder/f'{i}.tiff';tifffile.imwrite(path,xyz);paths.append(path)
    model=DepthBaseline(image_size=32);model.fit(paths[:3]);model.calibrate(paths[3:]);model.save(tmp_path/'depth.npz')
    loaded=DepthBaseline.load(tmp_path/'depth.npz')
    before,_=loaded.infer(paths[0]);xyz=tifffile.imread(paths[0]);xyz[10:16,10:16,2]+=.1
    defect=tmp_path/'defect.tiff';tifffile.imwrite(defect,xyz)
    after,amap=loaded.infer(defect)
    assert after>before and amap.shape==(32,32) and np.isfinite(amap).all()
    with pytest.raises(ValueError):loaded.fit([defect])
