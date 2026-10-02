"""MVTec AD discovery and explicit, reusable normal-only split manifests."""
import hashlib
import json
import random
from pathlib import Path

CATEGORIES = ("screw", "cable", "transistor")
EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def images(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*") if p.suffix.lower() in EXTENSIONS)


def validate_good(paths: list[Path]) -> None:
    if not paths or len(set(p.resolve() for p in paths)) != len(paths):
        raise ValueError("Require nonempty, unique GOOD images")
    for path in paths:
        if not path.is_file() or path.parent.name != "good" or path.parent.parent.name != "train":
            raise ValueError(f"Only train/good images are allowed: {path}")


def create_manifest(root: Path, category: str, destination: Path, shots: int = 30,
                    seed: int = 42, calibration_count: int = 20) -> None:
    """Explicit creation only; Member 1 must approve/reuse this exact manifest."""
    if destination.exists():
        raise FileExistsError(f"Will not overwrite shared subset: {destination}")
    if category not in CATEGORIES or shots not in (20, 30) or calibration_count < 1:
        raise ValueError("Use screw/cable/transistor, 20/30 shots, and held-out calibration")
    pool = images(root / category / "train" / "good")
    validate_good(pool)
    if len(pool) < shots + calibration_count:
        raise ValueError("Insufficient GOOD images for training and disjoint calibration")
    random.Random(seed).shuffle(pool)
    selected = pool[:shots + calibration_count]
    relative = [p.relative_to(root / category).as_posix() for p in selected]
    document = {"dataset": "mvtec_ad", "category": category, "seed": seed, "shots": shots,
                "train": relative[:shots], "calibration": relative[shots:],
                "sha256": {name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for name, p in zip(relative, selected)}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2) + "\n")


def load_manifest(root: Path, manifest: Path) -> tuple[dict, list[Path], list[Path]]:
    document = json.loads(manifest.read_text())
    category = document["category"]
    if document.get("dataset") != "mvtec_ad" or category not in CATEGORIES:
        raise ValueError("Unsupported dataset/category")
    base = (root / category).resolve()
    groups = []
    for key in ("train", "calibration"):
        paths = [(base / name).resolve() for name in document[key]]
        if any(not p.is_relative_to(base / "train" / "good") for p in paths):
            raise ValueError("Manifest may only reference category train/good files")
        validate_good(paths)
        groups.append(paths)
    train, calibration = groups
    if len(train) not in (20, 30) or len(train) != document["shots"]:
        raise ValueError("Manifest must contain exactly its declared 20/30 training shots")
    if set(train) & set(calibration):
        raise ValueError("Calibration must be held out from training")
    for path in train + calibration:
        name = path.relative_to(base).as_posix()
        expected = document.get("sha256", {}).get(name)
        if expected is None or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Missing or mismatched image hash: {name}")
    return document, train, calibration


def test_samples(root: Path, category: str) -> list[tuple[Path, int, Path | None]]:
    """Return untouched test set, with explicit missing masks rather than invented GT."""
    samples = []
    for folder in sorted((root / category / "test").glob("*")):
        if not folder.is_dir():
            continue
        for path in images(folder):
            label = int(folder.name != "good")
            mask = root / category / "ground_truth" / folder.name / f"{path.stem}_mask.png"
            samples.append((path, label, mask if label and mask.is_file() else None))
    if not samples:
        raise FileNotFoundError(f"No MVTec test images for {category}")
    return samples
