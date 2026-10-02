"""Decode/hash audit and frozen grouped development/final splits.

Official files remain untouched. Normal duplicates/corruption are excluded from
fitting; corrupt evaluation data is a blocking error rather than silently removed.
"""
import hashlib
import json
import random
from pathlib import Path
import numpy as np
from PIL import Image

EXTENSIONS={'.png','.jpg','.jpeg','.bmp','.tif','.tiff'}


def image_hash(path):
    with Image.open(path) as image:
        pixels=np.asarray(image.convert('RGB'))
        if pixels.ndim!=3 or min(pixels.shape[:2])<8:
            raise ValueError('Invalid image dimensions')
        digest=hashlib.sha256(str(pixels.shape).encode()+pixels.tobytes()).hexdigest()
        return digest,list(pixels.shape)


def discover(base: Path,dataset: str):
    if dataset=='mvtec_3d_ad':
        training=sorted((base/'train/good/rgb').glob('*.png'))
        testing=sorted((base/'test').glob('*/rgb/*.png'))
        def label(p): return int(p.parent.parent.name!='good')
        def masks(p):
            mask=p.parent.parent/'gt'/p.name
            return [mask] if mask.exists() else []
    else:
        training=sorted(p for p in (base/'train').rglob('*') if p.suffix.lower() in EXTENSIONS
                        and 'ground_truth' not in p.parts and 'mask' not in p.stem)
        # Public benchmark only; private AD2 data is excluded from local labelled metrics.
        testroot=base/('test_public' if (base/'test_public').exists() else 'test')
        testing=sorted(p for p in testroot.rglob('*') if p.suffix.lower() in EXTENSIONS
                       and not any(part in ('ground_truth','gt','masks') for part in p.relative_to(testroot).parts)
                       and not p.stem.endswith('_mask'))
        def label(p):
            return int(not any(part in ('good','normal') for part in p.relative_to(testroot).parts[:-1]))
        def masks(p):
            defect=p.relative_to(testroot).parts[0]
            candidates=[base/'ground_truth'/defect/f'{p.stem}_mask.png',base/'ground_truth'/defect/f'{p.stem}.png',
                        testroot/'ground_truth'/defect/f'{p.stem}_mask{p.suffix}',
                        testroot/'ground_truth'/defect/f'{p.stem}.png',p.parent/'ground_truth'/f'{p.stem}.png',
                        base/'ground_truth'/defect/p.stem]
            for candidate in candidates:
                if candidate.is_file(): return [candidate]
                if candidate.is_dir():
                    return sorted(q for q in candidate.rglob('*') if q.suffix.lower() in EXTENSIONS)
            return []
    if not training or not testing: raise ValueError(f'Unsupported or incomplete layout: {base}')
    return training,[(p,label(p),masks(p)) for p in testing]


def prepare(base: Path,dataset: str,category: str,output: Path,seed=42):
    output.mkdir(parents=True,exist_ok=True)
    manifest=output/'split.json'
    if manifest.exists():
        document=json.loads(manifest.read_text())
        for item in document['training']+document['calibration']+document['development']+document['final_test']:
            if image_hash(base/item['filename'])[0]!=item['sha256']:
                raise ValueError(f'Frozen split input changed: {item["filename"]}')
        return document
    training,testing=discover(base,dataset)
    audit={'corrupt_training':[],'duplicate_training':[],'train_evaluation_overlap':[],
           'duplicate_evaluation':[],'missing_defect_masks':[]}
    groups={}; evaluated=[]
    for path,label,masks in testing:
        digest,shape=image_hash(path)  # evaluation corruption blocks the category
        item={'filename':path.relative_to(base).as_posix(),'label':label,'sha256':digest,'shape':shape,
              'masks':[p.relative_to(base).as_posix() for p in masks]}
        if label and not masks: audit['missing_defect_masks'].append(item['filename'])
        for mask_path in masks:
            with Image.open(mask_path) as mask:
                mask.load()
                if list(mask.size)!=[shape[1],shape[0]]: raise ValueError(f'Mask geometry mismatch: {mask_path}')
        if digest in groups:
            if groups[digest][0]['label']!=label: raise ValueError('Duplicate images have conflicting labels')
            audit['duplicate_evaluation'].append(item['filename'])
        groups.setdefault(digest,[]).append(item); evaluated.append(item)
    seen=set(); clean=[]
    for path in training:
        try: digest,shape=image_hash(path)
        except Exception as error:
            audit['corrupt_training'].append({'file':path.relative_to(base).as_posix(),'error':str(error)}); continue
        name=path.relative_to(base).as_posix()
        if digest in groups: audit['train_evaluation_overlap'].append(name); continue
        if digest in seen: audit['duplicate_training'].append(name); continue
        seen.add(digest); clean.append({'filename':name,'label':0,'sha256':digest,'shape':shape,'masks':[]})
    rng=random.Random(seed); rng.shuffle(clean)
    calibration_count=max(20,round(.1*len(clean)))
    if len(clean)<calibration_count+30: raise ValueError('Insufficient clean training normals')
    calibration,fit=clean[:calibration_count],clean[calibration_count:]
    development,final=[],[]
    # Grouped per-label stratification prevents duplicate leakage across dev/final.
    for label in (0,1):
        keys=sorted(k for k,items in groups.items() if items[0]['label']==label)
        rng.shuffle(keys)
        if len(keys)<2: raise ValueError('Require both classes in development and final evaluation')
        count=max(1,round(.2*len(keys)))
        development.extend(item for k in keys[:count] for item in groups[k])
        final.extend(item for k in keys[count:] for item in groups[k])
    document={'dataset':dataset,'category':category,'seed':seed,'protocol':'normal_only_fit; grouped 20% labelled development / 80% held-out final test',
              'training':fit,'calibration':calibration,'development':sorted(development,key=lambda x:x['filename']),
              'final_test':sorted(final,key=lambda x:x['filename']),'audit':audit}
    manifest.write_text(json.dumps(document,indent=2)+'\n')
    return document


def canonical_training(base: Path,items: list,output: Path):
    """Canonical GOOD-only view; originals and official splits remain untouched."""
    folder=output/'train/good'; folder.mkdir(parents=True,exist_ok=True)
    paths=[]
    for item in items:
        source=base/item['filename']; target=folder/(item['sha256']+source.suffix.lower())
        if not target.exists(): target.hardlink_to(source)
        paths.append(target)
    return paths


def mask_array(base: Path,item: dict,size: int):
    if item['label']==0: return np.zeros((size,size),dtype=bool)
    if not item['masks']: return None
    mask=np.zeros((size,size),dtype=bool)
    for name in item['masks']:
        with Image.open(base/name) as image:
            mask|=np.asarray(image.convert('L').resize((size,size),Image.Resampling.NEAREST))>0
    return mask
