"""Development-selected fusion of saved anomaly models, without fitting defects."""
import io
import time
from dataclasses import replace
from pathlib import Path
import numpy as np
from PIL import Image
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.result import Prediction, normalize_score
from app.services.ml.shared.preprocessing import read_rgb


class EnsembleBaseline(Baseline):
    name = 'ensemble'

    def __init__(self, members, weights, category):
        if not members or len(members) != len(weights) or any(m.category != category for m in members):
            raise ValueError('Ensemble members must match the category')
        weights = np.asarray(weights, dtype=float)
        if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
            raise ValueError('Invalid ensemble weights')
        config = replace(members[0].config, image_size=max(m.config.image_size for m in members))
        super().__init__(config, category)
        self.members = members
        self.weights = (weights / weights.sum()).tolist()

    def fit(self, paths):
        raise RuntimeError('Fusion uses fitted normal-only members; select weights on development data')

    def infer(self, rgb):
        buffer = io.BytesIO()
        Image.fromarray(np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(buffer, format='PNG')
        result, amap = self.predict(buffer.getvalue())
        return result.anomaly_score, amap, None

    def predict(self, source, heatmap_path=None):
        import cv2
        if self.threshold is None:
            raise RuntimeError('Fusion threshold has not been selected')
        begin = time.perf_counter()
        score = 0.0
        amap = np.zeros((self.config.image_size, self.config.image_size), dtype=np.float32)
        for weight, member in zip(self.weights, self.members):
            result, member_map = member.predict(source)
            score += weight * normalize_score(result.anomaly_score, member.threshold)
            normalized = member_map / (member_map + member.threshold)
            amap += weight * cv2.resize(normalized, amap.shape[::-1])
        result = Prediction(self.provenance.get('dataset', 'mvtec_ad'), self.category, self.name,
                            score, self.threshold, str(heatmap_path) if heatmap_path else None,
                            (time.perf_counter() - begin) * 1000)
        if heatmap_path:
            from app.services.ml.shared.visualization import save_outputs
            save_outputs(read_rgb(source, self.config.image_size), amap, None, heatmap_path, self.threshold)
        return result, amap

    def save(self, path):
        import torch
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for index, member in enumerate(self.members):
            target = path.parent / f'{path.stem}_member_{index}.pt'
            member.save(target)
            records.append({'model': member.name, 'checkpoint': target.name})
        torch.save({**self.metadata(), 'members': records, 'weights': self.weights}, path)

    @classmethod
    def load(cls, path, device='cpu'):
        import torch
        from app.services.ml.factory import model_class
        path = Path(path)
        header = torch.load(path, map_location='cpu', weights_only=True)
        members = []
        for record in header['members']:
            target = (path.parent / record['checkpoint']).resolve()
            if not target.is_relative_to(path.parent.resolve()) or record['model'] == 'ensemble':
                raise ValueError('Invalid ensemble member checkpoint')
            members.append(model_class(record['model']).load(target, device))
        model = cls(members, header['weights'], header['category'])
        model.threshold = header['threshold']
        model.provenance = header['provenance']
        return model
