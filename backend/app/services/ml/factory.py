"""Lazy baseline imports keep normal backend operation free of ML dependencies."""
from importlib import import_module
from pathlib import Path


def model_class(name: str):
    if name == 'ensemble':
        from app.services.ml.ensemble import EnsembleBaseline
        return EnsembleBaseline
    if name == 'autoencoder':
        from app.services.ml.autoencoder.inference import AutoencoderBaseline
        return AutoencoderBaseline
    if name == 'padim':
        from app.services.ml.padim import PadimBaseline
        return PadimBaseline
    if name == 'patchcore':
        from app.services.ml.patchcore import PatchCoreBaseline
        return PatchCoreBaseline
    raise ValueError(f'Unknown baseline: {name}')


def load_patchcore(adapter: str, checkpoint: Path, device: str):
    """Member 1 supplies module:Class implementing the shared Baseline lifecycle.

    Only calls load; PatchCore is never retrained or modified by comparison.
    Checkpoint provenance must match comparison.provenance exactly.
    """
    module, name = adapter.split(':', 1)
    cls = getattr(import_module(module), name)
    return cls.load(checkpoint, device=device)
