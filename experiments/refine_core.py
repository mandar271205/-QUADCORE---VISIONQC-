"""Higher-resolution normal-only PatchCore trials with a bounded patch budget."""
import fcntl
import json
from pathlib import Path
import torch
from app.services.ml.patchcore import PatchCoreBaseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.preprocessing import read_rgb
from app.services.ml.shared.result import calibrate
from data_protocol import canonical_training
from train_suite import choose_threshold, score_samples, release

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/refined_f2'


def main():
    torch.set_num_threads(4)
    for category in ('screw', 'cable', 'transistor', 'metal_nut', 'capsule', 'bottle'):
        base = ROOT/'data/mvtec_ad'/category
        primary = ROOT/'outputs/training_f2/mvtec_ad'/category
        split = json.loads((primary/'split.json').read_text())
        folder = OUT/'mvtec_ad'/category
        folder.mkdir(parents=True, exist_ok=True)
        train = canonical_training(base, split['training'], ROOT/'data/curated/mvtec_ad'/category)
        calibration = canonical_training(base, split['calibration'], ROOT/'data/curated/mvtec_ad'/category)
        trials = []
        candidates = [{'image_size':384, 'backbone':'wide_resnet50_2', 'coreset_ratio':.02},
                      {'image_size':512, 'backbone':'resnet18', 'coreset_ratio':.03}]
        for index, parameters in enumerate(candidates):
            trial_dir = folder/f'trial_{index+1}'
            trial_dir.mkdir(exist_ok=True)
            record = trial_dir/'validation.json'
            if record.exists():
                trials.append(json.loads(record.read_text()))
                continue
            config = ExperimentConfig(image_size=parameters['image_size'], batch_size=2, device='mps')
            model = PatchCoreBaseline(config, category, backbone=parameters['backbone'],
                                      coreset_ratio=parameters['coreset_ratio'], max_training_patches=60000)
            try:
                model.fit(train)
                normals = [model.infer(read_rgb(p, config.image_size))[0] for p in calibration]
                model.threshold = calibrate(normals)
                _, predictions = score_samples(model, base, split['development'])
                model.threshold, _, threshold_trials = choose_threshold(normals, [i['label'] for i in split['development']],
                                                                        [p['anomaly_score'] for p in predictions])
                validation, _ = score_samples(model, base, split['development'])
                model.provenance = {'dataset':'mvtec_ad', 'category':category, 'selection':'development F2',
                                    'patch_sampling':'seeded equal budget per clean normal image', 'max_training_patches':60000}
                model.save(trial_dir/'model.pt')
                result = {'model':'patchcore', 'parameters':parameters|{'max_training_patches':60000},
                          'checkpoint':str((trial_dir/'model.pt').relative_to(ROOT)), 'validation':validation,
                          'threshold_trials':threshold_trials}
                record.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
                trials.append(result)
                print(category, parameters, validation, flush=True)
            finally:
                del model
                release()
        (folder/'validation_trials.json').write_text(json.dumps(trials, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    with (ROOT/'outputs/accelerator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
