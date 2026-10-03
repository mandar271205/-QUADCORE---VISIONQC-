"""Deployment boundaries, lossless upload pixels, and saved fusion equivalence."""
import io
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.services.heatmap.masks import validate_and_preprocess


def test_model_preprocessing_preserves_pixels():
    pixels = np.random.default_rng(42).integers(0, 256, (24, 1800, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format='PNG')
    _, inference = validate_and_preprocess(buffer.getvalue(), 'image/png', lossless_inference=True)
    np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(inference))), pixels)


@pytest.mark.asyncio
async def test_production_without_engine_cannot_return_demo(monkeypatch):
    from app.services.vlm.registry import VLMRegistry
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(VLMRegistry, 'get_ordered_engines', lambda: [])
    buffer = io.BytesIO()
    Image.new('RGB', (32, 32)).save(buffer, format='PNG')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/inspections', files={'image': ('frame.png', buffer.getvalue(), 'image/png')})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_profile_attachment_and_path_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ML_MODEL_ROOT', str(tmp_path))
    (tmp_path/'model.pt').write_bytes(b'catalog fixture, not loaded by this test')
    profile = {'id': 'mvtec_ad/screw', 'label': 'Screw', 'dataset': 'mvtec_ad', 'category': 'screw',
               'metrics': {'f2': .9, 'recall': .95, 'precision': .8, 'accuracy': .85},
               'definition': {'model': 'patchcore', 'checkpoint': 'model.pt'}}
    (tmp_path/'catalog.json').write_text(json.dumps({profile['id']: profile}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        public = (await client.get('/api/v1/products/trained-profiles')).json()
        assert len(public) == 1 and 'definition' not in public[0]
        product = (await client.post('/api/v1/products', json={'name': 'Screw', 'code': 'SCREW'})).json()
        response = await client.put(f"/api/v1/products/{product['id']}/model-profile", json={'profile_id': profile['id']})
        assert response.status_code == 200
        assert response.json()['model_status'] == 'ready'
        assert response.json()['threshold'] == .5
        assert json.loads((tmp_path/f"{product['id']}.json").read_text()) == profile['definition']
        invalid = await client.put(f"/api/v1/products/{product['id']}/model-profile", json={'profile_id': '../outside.pt'})
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_model_only_requires_a_trained_product(monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'INSPECTION_MODE', 'model_only')
    buffer = io.BytesIO()
    Image.new('RGB', (32, 32)).save(buffer, format='PNG')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/inspections', files={'image': ('frame.png', buffer.getvalue(), 'image/png')})
    assert response.status_code == 422
    assert 'trained inspection profile' in response.json()['detail']


def test_saved_fusion_preserves_prediction_and_map(tmp_path):
    pytest.importorskip('torch')
    from app.services.ml.autoencoder.inference import AutoencoderBaseline
    from app.services.ml.ensemble import EnsembleBaseline
    from app.services.ml.shared.config import ExperimentConfig
    good = tmp_path/'train/good'
    good.mkdir(parents=True)
    paths = []
    for index in range(4):
        path = good/f'{index}.png'
        Image.new('RGB', (32, 32), (100 + index, 100, 100)).save(path)
        paths.append(path)
    first = AutoencoderBaseline(ExperimentConfig(image_size=32, epochs=1), 'screw')
    first.fit(paths[:3])
    first.calibrate(paths[3:])
    second = AutoencoderBaseline(ExperimentConfig(image_size=32, epochs=1, seed=7), 'screw')
    second.fit(paths[:3])
    second.calibrate(paths[3:])
    fusion = EnsembleBaseline([first, second], [.25, .75], 'screw')
    fusion.threshold = .5
    before, amap = fusion.predict(paths[0])
    fusion.save(tmp_path/'fusion.pt')
    restored = EnsembleBaseline.load(tmp_path/'fusion.pt')
    after, bmap = restored.predict(paths[0])
    assert after.anomaly_score == pytest.approx(before.anomaly_score)
    assert after.verdict == before.verdict
    np.testing.assert_allclose(amap, bmap, atol=1e-6)


@pytest.mark.asyncio
async def test_real_comparison_api_uses_bounded_image_access(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ML_EXPERIMENT_ROOT', str(tmp_path))
    root = tmp_path/'30shot_f2'
    examples = root/'screw/padim/examples/test/good'
    examples.mkdir(parents=True)
    Image.new('RGB', (8, 8)).save(examples/'000_overlay.png')
    (root/'results.json').write_text(json.dumps([{'dataset':'fixture','category':'screw','model':'padim','f2':.75}]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/experiments/comparison')
        assert response.status_code == 200
        data = response.json()
        assert data['state'] == 'partial'
        assert data['results'][0]['f2'] == .75
        image = await client.get(data['results'][0]['examples'][0]['url'])
        assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
        forbidden = await client.get('/api/v1/experiments/examples/%2E%2E/outside.png')
        assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_system_readiness_requires_an_actual_engine(monkeypatch):
    from app.api.v1 import system
    async def healthy_database(): return True
    monkeypatch.setattr(system,'check_db_health',healthy_database)
    monkeypatch.setattr(system.storage_service,'is_available',lambda:False)
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'ML_ENABLED',False)
    monkeypatch.setattr(settings,'INSPECTION_MODE','model_only')
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        status=(await client.get('/api/v1/system/status')).json()
        assert status['inspection_available'] is False
        assert status['database_available'] is True
        assert status['storage_available'] is True
        assert isinstance(status['vlm_available'], bool)
        assert status['member1_runtime']['enabled'] is False
        assert status['member1_runtime']['worker_alive'] is False
        assert status['member2_runtime']['enabled'] is False
        product=(await client.post('/api/v1/products',json={'name':'UTC fixture','code':'UTC'})).json()
        assert product['created_at'].endswith('Z')


@pytest.mark.asyncio
async def test_roi_box_is_drawn_in_existing_heatmap_response(monkeypatch):
    import base64
    from app.services.ml.base import MLInspectionResult
    from app.services.ml.registry import MLRegistry
    class ROIEngine:
        def is_model_available(self, product_id=None): return product_id is not None
        async def inspect(self, image_bytes, product_id=None):
            return MLInspectionResult(anomaly_score=.8, anomaly_map=np.zeros((80,100),dtype=np.float32),
                                      roi_region={'x':.3,'y':.25,'width':.4,'height':.5})
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'ML_ENABLED',True)
    monkeypatch.setattr(settings,'INSPECTION_MODE','model_only')
    monkeypatch.setattr(MLRegistry,'_engines',[ROIEngine()])
    buffer=io.BytesIO();Image.new('RGB',(100,80)).save(buffer,format='PNG')
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        product=(await client.post('/api/v1/products',json={'name':'ROI fixture','code':'ROI'})).json()
        response=await client.post('/api/v1/inspections',data={'product_id':product['id']},
            files={'image':('frame.png',buffer.getvalue(),'image/png')})
        assert response.status_code==201,response.text
        url=response.json()['heatmap_url']
        heatmap=np.asarray(Image.open(io.BytesIO(base64.b64decode(url.split(',',1)[1]))))
        assert heatmap[20,30].tolist()==[0,255,0]


@pytest.mark.asyncio
@pytest.mark.parametrize('configured,override,client_type,mobile_ml,expected_status,lossless', [
    ('vlm_primary','model_only','web',True,422,True),
    ('model_only','vlm_only','web',True,503,False),
    ('model_only',None,'mobile',False,503,False),
    ('model_only','invalid','web',True,422,True),
])
async def test_upload_mode_consistent_with_engine_route(monkeypatch, configured, override,
                                                       client_type, mobile_ml, expected_status, lossless):
    from app.api.v1 import inspections
    from app.services.vlm.registry import VLMRegistry
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'ML_ENABLED',False)
    monkeypatch.setattr(settings,'INSPECTION_MODE',configured)
    monkeypatch.setattr(settings,'MOBILE_USE_ML',mobile_ml)
    monkeypatch.setattr(VLMRegistry,'get_ordered_engines',lambda:[])
    calls=[]
    original=inspections.validate_and_preprocess
    def preprocess(*args,**kwargs):
        calls.append(kwargs['lossless_inference'])
        return original(*args,**kwargs)
    monkeypatch.setattr(inspections,'validate_and_preprocess',preprocess)
    buffer=io.BytesIO();Image.new('RGB',(32,32)).save(buffer,format='PNG')
    data={'client_type':client_type}
    if override is not None:data['inspection_mode']=override
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/api/v1/inspections',data=data,
            files={'image':('frame.png',buffer.getvalue(),'image/png')})
    assert response.status_code==expected_status,response.text
    assert calls==[lossless]
