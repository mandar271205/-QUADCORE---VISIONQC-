"""Optional aligned depth baseline, not a research-grade 3D point-cloud model."""
import json
from pathlib import Path
import cv2
import numpy as np
import tifffile
from app.services.ml.shared.result import calibrate


class DepthBaseline:
    name='depth_gaussian'
    def __init__(self,image_size=128,regularization=1e-4):
        self.image_size=image_size;self.regularization=regularization
        self.mean=None;self.variance=None;self.threshold=None

    def features(self,path: Path):
        xyz=tifffile.imread(path).astype(np.float32)
        if xyz.ndim!=3 or xyz.shape[-1]!=3 or not np.isfinite(xyz).all():
            raise ValueError(f'Expected finite HxWx3 XYZ TIFF: {path}')
        z=xyz[:,:,2];valid=np.any(xyz!=0,axis=2)
        if not valid.any():raise ValueError(f'Empty depth scan: {path}')
        centered=np.where(valid,z-np.median(z[valid]),0)
        depth=cv2.resize(centered,(self.image_size,self.image_size),interpolation=cv2.INTER_LINEAR)
        mask=cv2.resize(valid.astype(np.uint8),(self.image_size,self.image_size),interpolation=cv2.INTER_NEAREST).astype(bool)
        dx=cv2.Sobel(depth,cv2.CV_32F,1,0,ksize=3)/8
        dy=cv2.Sobel(depth,cv2.CV_32F,0,1,ksize=3)/8
        return np.stack([depth,dx,dy],axis=2),mask

    def fit(self,paths):
        if not paths:raise ValueError('Nonempty normal depth scans required')
        for path in paths:
            if path.parent.name!='xyz' or path.parent.parent.name!='good' or path.parent.parent.parent.name!='train':
                raise ValueError('Fit may only use train/good/xyz scans')
        features=np.stack([self.features(path)[0] for path in paths])
        self.mean=features.mean(axis=0);self.variance=features.var(axis=0)+self.regularization

    def infer(self,path):
        if self.mean is None:raise RuntimeError('Depth model is not fitted')
        features,valid=self.features(path)
        amap=np.sqrt(((features-self.mean)**2/self.variance).mean(axis=2))
        amap=cv2.GaussianBlur(amap,(5,5),1);amap=np.where(valid,amap,0).astype(np.float32)
        return float(np.percentile(amap[valid],99.5)),amap

    def calibrate(self,paths,percentile=99):
        self.threshold=calibrate([self.infer(path)[0] for path in paths],percentile)

    def save(self,path):
        if self.threshold is None:raise RuntimeError('Calibrate before saving')
        path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path,mean=self.mean,variance=self.variance,image_size=self.image_size,
                            regularization=self.regularization,threshold=self.threshold)

    @classmethod
    def load(cls,path):
        checkpoint=np.load(path,allow_pickle=False)
        instance=cls(int(checkpoint['image_size']),float(checkpoint['regularization']))
        instance.mean=checkpoint['mean'];instance.variance=checkpoint['variance'];instance.threshold=float(checkpoint['threshold'])
        return instance
