"""Verify real baseline inference through the existing adapter/router/API."""
import io
import json
import uuid
import numpy as np
import pytest
from PIL import Image
from httpx import AsyncClient, ASGITransport
from app.core.config import settings
from app.services.ml.profile_engine import ProfileMLEngine
from app.services.ml.registry import MLRegistry
from app.services.ml.shared.config import ExperimentConfig
from app.main import app


@pytest.mark.asyncio
async def test_baseline_registered_backend_inspection(tmp_path, monkeypatch):
    pytest.importorskip('torch')
    from app.services.ml.autoencoder.inference import AutoencoderBaseline
    good = tmp_path/'train/good'; good.mkdir(parents=True)
    paths=[]
    for i in range(4):
        path=good/f'{i}.png'; Image.new('RGB',(32,32),(100+i,100,100)).save(path); paths.append(path)
    model = AutoencoderBaseline(ExperimentConfig(image_size=32,epochs=1),'screw')
    model.fit(paths[:3]); model.calibrate(paths[3:])
    profile_root=tmp_path/'profiles'; profile_root.mkdir(); model.save(profile_root/'screw.pt')
    monkeypatch.setattr(settings,'ML_MODEL_ROOT',str(profile_root))
    monkeypatch.setattr(settings,'ML_ENABLED',True)
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    engine=ProfileMLEngine(); monkeypatch.setattr(MLRegistry,'_engines',[engine])
    assert not engine.is_model_available('../../outside')
    assert not engine.is_model_available(str(uuid.uuid4()))
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        product = (await client.post('/api/v1/products',json={'name':'Fixture product','code':'ML-FIXTURE','threshold':.5})).json()
        product_id=product['id']
        definition=profile_root/f'{product_id}.json'
        definition.write_text(json.dumps({'model':'autoencoder','checkpoint':'screw.pt'}))
        assert MLRegistry.get(product_id) is engine
        assert await engine.load_model(product_id)
        buffer=io.BytesIO(); Image.new('RGB',(64,48),(100,100,100)).save(buffer,format='PNG')
        result=await engine.inspect(buffer.getvalue(),product_id)
        assert 0 <= result.anomaly_score <= 1 and result.confidence is None
        assert result.anomaly_map.shape==(32,32)
        response=await client.post('/api/v1/inspections',data={'product_id':product_id,'inspection_mode':'model_only'},
                                  files={'image':('frame.png',buffer.getvalue(),'image/png')})
        assert response.status_code==201, response.text
        public=response.json()
        assert public['confidence']==0.0  # unavailable, never an invented defect probability
        assert public['heatmap_url'] is not None
        assert 'model_name' not in public and 'provider' not in public
        definition.write_text(json.dumps({'model':'autoencoder','checkpoint':'../screw.pt'}))
        assert not engine.is_model_available(product_id)


@pytest.mark.asyncio
async def test_roi_backend_map_projects_to_frame(tmp_path,monkeypatch):
    from app.services.ml.roi import OpenCVROIExtractor
    from app.services.ml.shared.result import Prediction
    class Stub:
        name='patchcore'; threshold=1
        def predict(self,source):
            return Prediction('mvtec_ad','screw',self.name,2,1,None,1),np.ones((16,16),dtype=np.float32)
    engine=ProfileMLEngine()
    monkeypatch.setattr(engine,'_load',lambda _: (Stub(),OpenCVROIExtractor()))
    image=np.zeros((80,100,3),dtype=np.uint8); image[20:60,30:70]=255
    buffer=io.BytesIO(); Image.fromarray(image).save(buffer,format='PNG')
    result=await engine.inspect(buffer.getvalue(),str(uuid.uuid4()))
    assert result.anomaly_map.shape==(80,100)
    assert result.anomaly_map[:20].sum()==0
    assert result.anomaly_map[20:60,30:70].mean()==.5
    assert result.roi_region=={'x':.3,'y':.25,'width':.4,'height':.5}
    empty=io.BytesIO(); Image.new('RGB',(80,100)).save(empty,format='PNG')
    with pytest.raises(ValueError,match='No product ROI'):
        await engine.inspect(empty.getvalue(),str(uuid.uuid4()))
