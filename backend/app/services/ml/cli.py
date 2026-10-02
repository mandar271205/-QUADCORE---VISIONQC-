"""Run with PYTHONPATH=backend python -m app.services.ml.cli --help."""
import argparse
import json
from pathlib import Path
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.data import CATEGORIES, create_manifest, load_manifest
from app.services.ml.factory import model_class, load_patchcore
from app.services.ml.comparison import provenance, run_comparison, aggregate_reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    subset = sub.add_parser('subset', help='Explicitly create a shared subset; coordinate with Member 1')
    subset.add_argument('--data-root', type=Path, default=Path('data/mvtec_ad'))
    subset.add_argument('--category', choices=CATEGORIES, required=True)
    subset.add_argument('--manifest', type=Path, required=True)
    subset.add_argument('--shots', type=int, choices=(20,30), default=30)
    subset.add_argument('--calibration-count', type=int, default=20)
    subset.add_argument('--seed', type=int, default=42)
    for command in ('train', 'compare'):
        p = sub.add_parser(command)
        p.add_argument('--data-root', type=Path, default=Path('data/mvtec_ad'))
        p.add_argument('--manifest', type=Path, required=True)
        p.add_argument('--output', type=Path, default=Path('outputs'))
        p.add_argument('--image-size', type=int, default=256)
        p.add_argument('--device', default='cpu')
        p.add_argument('--seed', type=int, default=42)
        if command == 'train':
            p.add_argument('--model', choices=('autoencoder','padim'), required=True)
            p.add_argument('--epochs', type=int, default=50)
            p.add_argument('--batch-size', type=int, default=8)
            p.add_argument('--learning-rate', type=float, default=.001)
            p.add_argument('--percentile', type=float, default=99)
            p.add_argument('--threshold', type=float, help='Optional explicit raw-score threshold')
        else:
            p.add_argument('--patchcore-adapter', help='Member 1 module:Class, implementing Baseline')
            p.add_argument('--patchcore-checkpoint', type=Path)
            p.add_argument('--allow-20-shot', action='store_true', help='Primary comparison otherwise requires 30')
    predict = sub.add_parser('predict')
    predict.add_argument('--model', choices=('autoencoder','padim'), required=True)
    predict.add_argument('--checkpoint', type=Path, required=True)
    predict.add_argument('--image', type=Path, required=True)
    predict.add_argument('--heatmap', type=Path, required=True)
    predict.add_argument('--device', default='cpu')
    roi = sub.add_parser('roi-compare', help='Optional PatchCore full-frame/ROI ablation')
    roi.add_argument('--data-root', type=Path, default=Path('data/mvtec_ad'))
    roi.add_argument('--category', choices=CATEGORIES, required=True)
    roi.add_argument('--patchcore-adapter', required=True)
    roi.add_argument('--checkpoint', type=Path, required=True)
    roi.add_argument('--roi-checkpoint', type=Path)
    roi.add_argument('--extractor', choices=('opencv','yolo'), default='opencv')
    roi.add_argument('--roi-weights', type=Path)
    roi.add_argument('--device', default='cpu')
    roi.add_argument('--output', type=Path, default=Path('outputs/roi'))
    args = parser.parse_args()
    if args.command == 'subset':
        create_manifest(args.data_root,args.category,args.manifest,args.shots,args.seed,args.calibration_count)
        print(f'Saved shared subset: {args.manifest}. All three models must use this exact manifest.')
        return
    if args.command == 'roi-compare':
        from app.services.ml.roi import OpenCVROIExtractor, YOLOROIExtractor
        from app.services.ml.roi_experiment import run_roi_experiment
        if args.extractor == 'yolo' and args.roi_weights is None:
            parser.error('YOLO requires separately trained --roi-weights')
        extractor = OpenCVROIExtractor() if args.extractor == 'opencv' else YOLOROIExtractor(args.roi_weights)
        model = load_patchcore(args.patchcore_adapter,args.checkpoint,args.device)
        cropped = load_patchcore(args.patchcore_adapter,args.roi_checkpoint,args.device) if args.roi_checkpoint else None
        run_roi_experiment(args.data_root,args.category,model,extractor,args.output/args.category,cropped)
        print(f'Saved ROI ablation in {args.output/args.category}')
        return
    if args.command == 'predict':
        model = model_class(args.model).load(args.checkpoint, args.device)
        result, _ = model.predict(args.image,args.heatmap)
        print(json.dumps(result.to_dict(), indent=2))
        return
    try:
        document, train, calibration = load_manifest(args.data_root,args.manifest)
    except (FileNotFoundError, ValueError, KeyError) as error:
        parser.error(f'Cannot use shared subset: {error}. Supply real MVTec data and Member 1 manifest.')
    category = document['category']
    if args.command == 'train':
        config = ExperimentConfig(args.image_size,args.seed,args.epochs,args.batch_size,
                                  args.learning_rate,args.percentile,args.device)
        model = model_class(args.model)(config,category)
        model.fit(train)
        model.calibrate(calibration)
        if args.threshold is not None:
            if args.threshold <= 0 or not __import__('math').isfinite(args.threshold):
                parser.error('Explicit threshold must be finite and positive')
            model.threshold = args.threshold
        model.provenance = provenance(document,config)
        checkpoint = args.output/'checkpoints'/args.model/f'{category}.pt'
        model.save(checkpoint)
        _, _ = model.predict(calibration[0],args.output/'heatmaps'/args.model/category/'calibration.png')
        print(f'Saved {checkpoint}; threshold={model.threshold}; training shots={len(train)}')
        return
    if document['shots'] != 30 and not args.allow_20_shot:
        parser.error('Primary comparison requires exactly 30 GOOD images')
    config = ExperimentConfig(image_size=args.image_size,seed=args.seed,device=args.device)
    models = {}
    for name in ('autoencoder','padim'):
        path = args.output/'checkpoints'/name/f'{category}.pt'
        if path.is_file():
            models[name] = model_class(name).load(path,args.device)
    if bool(args.patchcore_adapter) != bool(args.patchcore_checkpoint):
        parser.error('Supply both PatchCore adapter and checkpoint')
    if args.patchcore_adapter:
        models['patchcore'] = load_patchcore(args.patchcore_adapter,args.patchcore_checkpoint,args.device)
    run_comparison(args.data_root,args.manifest,models,args.output,config)
    aggregate_reports(args.output)
    print(f'Saved comparison CSV/JSON in {args.output}; missing models explicitly marked unavailable')


if __name__ == '__main__':
    main()
