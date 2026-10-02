"""Anomalib PatchCore adapter added for the user's expanded training request.

This does not replace any Member 1 model (none exists in this checkout).
"""
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
import numpy as np
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.data import validate_good
from app.services.ml.shared.preprocessing import seed_everything, read_rgb, tensor


class PatchCoreBaseline(Baseline):
    name = 'patchcore'

    def __init__(self, config: ExperimentConfig, category: str, backbone: str = 'resnet18',
                 coreset_ratio: float = .02, num_neighbors: int = 9, *, initialize_pretrained: bool = True,
                 max_training_patches: int | None = None):
        super().__init__(config,category)
        if version('anomalib') != '2.3.0':
            raise RuntimeError('This adapter requires Anomalib 2.3.0')
        if not 0 < coreset_ratio <= 1:
            raise ValueError('Invalid coreset sampling ratio')
        if max_training_patches is not None and max_training_patches < num_neighbors:
            raise ValueError('Patch budget must exceed neighbor count')
        self.max_training_patches = max_training_patches
        import torch
        from anomalib.models import Patchcore
        seed_everything(config.seed)
        self.backbone,self.coreset_ratio,self.num_neighbors = backbone,coreset_ratio,num_neighbors
        self.model=Patchcore(backbone=backbone,layers=['layer2','layer3'],pre_trained=initialize_pretrained,
                             coreset_sampling_ratio=coreset_ratio,num_neighbors=num_neighbors,
                             pre_processor=False,post_processor=False,evaluator=False,visualizer=False).model.to(config.device)
        self.mean=torch.tensor([.485,.456,.406],device=config.device).view(1,3,1,1)
        self.std=torch.tensor([.229,.224,.225],device=config.device).view(1,3,1,1)
        self.fitted=False

    def _input(self,rgb):
        return (tensor(rgb,self.config.device)-self.mean)/self.std

    def fit(self,paths: list[Path]) -> None:
        import torch
        validate_good(paths)
        self.training_paths={p.resolve() for p in paths}
        seed_everything(self.config.seed)
        self.model.embedding_store=[]
        self.model.train(); self.model.feature_extractor.eval()
        generator = torch.Generator().manual_seed(self.config.seed)
        budget = max(1, self.max_training_patches // len(paths)) if self.max_training_patches else None
        with torch.no_grad():
            for offset in range(0,len(paths),self.config.batch_size):
                batch=torch.cat([self._input(read_rgb(p,self.config.image_size))
                                 for p in paths[offset:offset+self.config.batch_size]])
                self.model(batch)
                if budget is not None:
                    embedding = self.model.embedding_store.pop()
                    per_image = embedding.reshape(len(batch), -1, embedding.shape[-1])
                    for patches in per_image:
                        indices = torch.randperm(len(patches), generator=generator)[:budget].to(patches.device)
                        self.model.embedding_store.append(patches.index_select(0, indices).cpu())
            # Sampling is done on CPU: MPS sparse random projection is unsupported.
            self.model.embedding_store=[embedding.cpu() for embedding in self.model.embedding_store]
            self.model.subsample_embedding(self.coreset_ratio)
            self.model.memory_bank=self.model.memory_bank.to(self.config.device)
        if len(self.model.memory_bank) < self.num_neighbors:
            raise ValueError('Coreset must contain at least num_neighbors patches')
        self.model.eval(); self.fitted=True; self.threshold=None

    def infer(self,rgb: np.ndarray):
        import torch
        if not self.fitted:
            raise RuntimeError('PatchCore memory bank is not fitted')
        with torch.inference_mode():
            output=self.model(self._input(rgb))
            anomaly_map=output.anomaly_map[0,0].cpu().numpy()
            score=float(output.pred_score.reshape(-1)[0].cpu())
        return score,anomaly_map,None

    def save(self,path: Path) -> None:
        import torch
        path.parent.mkdir(parents=True,exist_ok=True)
        torch.save({**self.metadata(),'state_dict':self.model.state_dict(),'anomalib_version':version('anomalib'),
                    'backbone':self.backbone,'coreset_ratio':self.coreset_ratio,'num_neighbors':self.num_neighbors,
                    'max_training_patches':self.max_training_patches},path)

    @classmethod
    def load(cls,path: Path,device: str='cpu'):
        import torch
        checkpoint=torch.load(path,map_location=device,weights_only=True)
        if checkpoint['model']!=cls.name or checkpoint['anomalib_version']!='2.3.0':
            raise ValueError('Incompatible PatchCore checkpoint')
        config=replace(ExperimentConfig(**checkpoint['config']),device=device)
        model=cls(config,checkpoint['category'],checkpoint['backbone'],checkpoint['coreset_ratio'],
                  checkpoint['num_neighbors'],initialize_pretrained=False,
                  max_training_patches=checkpoint.get('max_training_patches'))
        model.model.load_state_dict(checkpoint['state_dict']); model.model.eval()
        model.threshold=checkpoint['threshold']; model.provenance=checkpoint['provenance']; model.fitted=True
        return model
