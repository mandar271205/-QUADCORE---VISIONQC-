"""Export development-selected checkpoints into the existing profile engine root."""
import asyncio
import json
import shutil
import hashlib
from pathlib import Path
from sqlalchemy import select
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.db.models import Product, ModelStatus
from app.services.ml.catalog import register_profile

ROOT = Path(__file__).resolve().parents[1]


def checkpoint_parameters(path):
    import torch
    header = torch.load(path, map_location='cpu', weights_only=True, mmap=True)
    parameters = {key: header[key] for key in ('model','config','threshold','backbone','coreset_ratio',
                  'num_neighbors','n_features','max_training_patches','weights') if key in header}
    if 'members' in header:
        members = []
        for record in header['members']:
            target = (path.parent/record['checkpoint']).resolve()
            if not target.is_relative_to(path.parent.resolve()):
                raise ValueError('Invalid member checkpoint path')
            members.append(checkpoint_parameters(target))
        parameters['members'] = members
    return parameters


def export():
    output = Path(settings.ML_MODEL_ROOT).resolve()
    output.mkdir(parents=True, exist_ok=True)
    catalog_path = output / 'catalog.json'
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    for path in sorted((ROOT / 'outputs/training_f2').glob('*/*/results.json')):
        report = json.loads(path.read_text())
        dataset, category = report['dataset'], report['category']
        key = dataset + '/' + category
        improved = ROOT / 'outputs/improved_f2' / dataset / category / 'results.json'
        selected = next(r for r in report['final_results'] if r['selected_for_deployment'])
        if improved.exists():
            final = json.loads(improved.read_text())
            checkpoint = ROOT / final['checkpoint']
            model, metrics, validation = 'ensemble', final['final_metrics'], final['validation']
            sources = list(checkpoint.parent.glob('*.pt'))
        else:
            chosen = next(t for t in report['trials'] if t['model'] == selected['model'] and t['parameters'] == selected['parameters'])
            checkpoint = ROOT / chosen['checkpoint']
            model, metrics, validation = selected['model'], selected, chosen['validation']
            sources = [checkpoint]
        # Versioned exports keep existing product profiles stable until explicitly reattached.
        digest=hashlib.sha256()
        for source in sorted(sources):
            digest.update(source.name.encode())
            with source.open('rb') as stream:
                digest.update(hashlib.file_digest(stream,'sha256').digest())
        version = model+'_'+digest.hexdigest()[:16]
        target = output / 'checkpoints' / dataset / category / version
        target.mkdir(parents=True, exist_ok=True)
        for source in sources:
            destination = target / source.name
            if not destination.exists():
                temporary = destination.with_suffix('.tmp')
                shutil.copy2(source, temporary)
                temporary.replace(destination)
        definition = {'model': model, 'checkpoint': str((target / checkpoint.name).relative_to(output)),
                      'dataset': dataset, 'category': category, 'selection_metric': 'development F2'}
        catalog[key] = {'id': key, 'label': f'{category.replace("_", " ").title()} ({dataset})',
                        'dataset': dataset, 'category': category,
                        'metrics': {k: metrics.get(k) for k in ('f2', 'f1', 'precision', 'recall', 'accuracy',
                                    'balanced_accuracy', 'image_auroc', 'pixel_auroc', 'average_precision',
                                    'confusion_matrix', 'false_accept_rate', 'false_reject_rate', 'latency_ms')},
                        'validation': validation, 'definition': definition,
                        'checkpoint_parameters': checkpoint_parameters(checkpoint),
                        'prior_final_test_exposure': improved.exists() or report['prior_final_test_exposure']}
    temporary = catalog_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(catalog, indent=2, allow_nan=False) + '\n')
    temporary.replace(catalog_path)
    core={key:value for key,value in catalog.items() if key.startswith('mvtec_ad/')}
    if len(core)==6:
        tn,fp,fn,tp=[sum(p['metrics']['confusion_matrix'][r][c] for p in core.values())
                     for r,c in ((0,0),(0,1),(1,0),(1,1))]
        pooled={'test_images':tn+fp+fn+tp,'confusion_matrix':[[tn,fp],[fn,tp]],
                'accuracy':(tn+tp)/max(1,tn+fp+fn+tp),'precision':tp/max(1,tp+fp),
                'recall':tp/max(1,tp+fn),'f1':2*tp/max(1,2*tp+fp+fn),
                'f2':5*tp/max(1,5*tp+fp+4*fn)}
        folder=ROOT/'outputs/final_core';folder.mkdir(parents=True,exist_ok=True)
        (folder/'models.json').write_text(json.dumps({'selection':'development F2; accuracy and AUROC ties; preserve existing deployment on exact tie',
                     'model_root':str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
                     'profiles':core,'pooled_core_decision_metrics':pooled,
                     'aggregation_scope':'Six category-specific profiles; pooled decisions weight each final image equally. This is not a single universal model.',
                     'evaluation_limitations':'Frozen local final splits were previously evaluated; new tuning uses development data only. Scores are not official full-benchmark metrics.'},indent=2,allow_nan=False)+'\n')
        lines=['# Final core deployment models','',
               'Six category-specific profiles selected using development F2. Runtime checkpoint paths are relative to ML_MODEL_ROOT.','',
               '| Category | F2 | Recall | Precision | F1 | Accuracy | Image AUROC | Pixel AUROC |',
               '|---|---:|---:|---:|---:|---:|---:|---:|']
        for key,value in sorted(core.items()):
            metrics=value['metrics']
            lines.append('| '+value['category']+' | '+' | '.join('Unavailable' if metrics[k] is None else f'{100*metrics[k]:.2f}%' for k in ('f2','recall','precision','f1','accuracy','image_auroc','pixel_auroc'))+' |')
        lines+=['','Choose the matching product in the existing frontend, upload its image, and run inspection. The saved profile performs inference without retraining. The API returns the score, PASS/FAIL (or configured REVIEW), heatmap, and inspection history.',
                '', f"Pooled decisions across {pooled['test_images']} frozen final images: accuracy {100*pooled['accuracy']:.2f}%, F2 {100*pooled['f2']:.2f}%, F1 {100*pooled['f1']:.2f}%, precision {100*pooled['precision']:.2f}%, recall {100*pooled['recall']:.2f}%. These aggregate six category-specific profiles, not a universal model.",
                '', 'Anomaly scores are display values, not probabilities. CPU deployment latency differs from MPS benchmark latency.','',
                'All scores use previously evaluated frozen local final splits. Refinement uses development labels only; a global optimum or perfect accuracy is not established.',
                '', 'The 30-shot comparison, ROI ablations, and extended D2S/depth experiments are separate artifacts. Completion of this core export does not imply those extended jobs are complete.']
        (folder/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return catalog


async def seed_profiles(catalog):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        for key, profile in catalog.items():
            code = key.replace('/', '-').upper()
            product = (await session.execute(select(Product).where(Product.code == code))).scalar_one_or_none()
            if product is None:
                product = Product(name=profile['label'], code=code, description='Benchmark profile: use matching product and image conditions.',
                                  threshold=.5, model_status=ModelStatus.ready)
                session.add(product)
                await session.flush()
            register_profile(str(product.id), key)
            product.model_status = ModelStatus.ready
        await session.commit()
    await engine.dispose()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed-products', action='store_true')
    args = parser.parse_args()
    catalog = export()
    print('Exported profiles:', list(catalog), flush=True)
    if args.seed_products:
        asyncio.run(seed_profiles(catalog))
