"""Compare real saved-model predictions with the running existing upload API."""
import argparse
import gc
import json
import mimetypes
from pathlib import Path
import requests
import torch
from app.services.ml.factory import model_class
from app.services.ml.shared.result import normalize_score

ROOT=Path(__file__).resolve().parents[1]


def main(base_url, all_profiles=False):
    torch.set_num_threads(4)
    products=requests.get(base_url+'/products',timeout=30).json()
    catalog=json.loads((ROOT/'models/catalog.json').read_text())
    rows=[]
    keys=sorted(catalog) if all_profiles else ['mvtec_ad/'+category for category in
             ('screw','cable','transistor','metal_nut','capsule','bottle')]
    for key in keys:
        profile=catalog[key]
        dataset,category=key.split('/')
        product=next(p for p in products if p['code']==key.replace('/','-').upper())
        model=model_class(profile['definition']['model']).load(ROOT/'models'/profile['definition']['checkpoint'],'cpu')
        split=json.loads((ROOT/'outputs/training_f2'/dataset/category/'split.json').read_text())
        for label in (0,1):
            item=next(i for i in split['final_test'] if i['label']==label)
            source=ROOT/'data'/dataset/category/item['filename']
            predicted,_=model.predict(source)
            with source.open('rb') as image:
                response=requests.post(base_url+'/inspections',data={'product_id':product['id'],'client_type':'web'},
                    files={'image':(source.name,image,mimetypes.guess_type(source.name)[0] or 'image/png')},timeout=90)
            response.raise_for_status();actual=response.json()
            assert actual['decision']==predicted.verdict,(category,item['filename'],actual['decision'],predicted.verdict)
            expected=normalize_score(predicted.anomaly_score,predicted.threshold)
            assert abs(expected-actual['anomaly_score'])<1e-5,(category,expected,actual['anomaly_score'])
            assert actual['original_image_url'] and actual['heatmap_url']
            assert actual['confidence']==0
            assert 'provider' not in actual and 'model_name' not in actual
            persisted=requests.get(base_url+'/inspections/'+actual['inspection_id'],timeout=30).json()
            assert persisted['decision']==actual['decision'] and persisted['heatmap_url']==actual['heatmap_url']
            rows.append({'dataset':dataset,'category':category,'filename':item['filename'],'ground_truth':label,
                         'decision':actual['decision'],'expected_saved_model_decision':predicted.verdict,
                         'score_difference':abs(expected-actual['anomaly_score']),
                         'processing_time_ms':actual['processing_time_ms'],'heatmap_present':True,'history_verified':True})
            print(rows[-1],flush=True)
        del model;gc.collect()
    report=requests.get(base_url+'/experiments/comparison',timeout=30).json()
    assert report['state']=='complete' and len(report['results'])==9
    for row in report['results']:
        assert len(row['examples'])==10,(row['category'],row['model'],len(row['examples']))
        assert requests.get(row['examples'][0]['url'],timeout=30).status_code==200
    output=ROOT/'outputs/validation';output.mkdir(parents=True,exist_ok=True)
    (output/('upload_all_profiles_e2e.json' if all_profiles else 'upload_e2e.json')).write_text(json.dumps({'state':'passed','scope':'Saved model/API parity and storage/history, not additional performance tuning',
                                                  'uploads':rows,'comparison_rows':9},indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--api',default='http://127.0.0.1:8001/api/v1')
    parser.add_argument('--all-profiles',action='store_true');args=parser.parse_args()
    main(args.api,args.all_profiles)
