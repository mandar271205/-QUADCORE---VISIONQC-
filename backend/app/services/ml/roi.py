"""Optional product ROI extraction, independent of anomaly detectors.

OpenCV is a demonstration fallback, not a D2S-trained segmentation model.
YOLOROIExtractor accepts separately trained segmentation weights (e.g. D2S).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np


@dataclass
class ROI:
    bbox: tuple[int,int,int,int]  # x1,y1,x2,y2; exclusive end coordinates
    mask: np.ndarray

    def crop(self, image: np.ndarray) -> np.ndarray:
        x1,y1,x2,y2 = self.bbox
        return image[y1:y2,x1:x2].copy()


class ROIExtractor(ABC):
    @abstractmethod
    def extract(self, image: np.ndarray) -> ROI | None: ...


class OpenCVROIExtractor(ROIExtractor):
    def __init__(self, min_area_fraction: float = .01):
        if not 0 < min_area_fraction < 1:
            raise ValueError('min_area_fraction must be in (0,1)')
        self.min_area_fraction = min_area_fraction

    def extract(self, image: np.ndarray) -> ROI | None:
        gray = cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
        # Estimate a uniform background from the border, then find the largest object.
        border = np.concatenate((gray[0],gray[-1],gray[:,0],gray[:,-1]))
        contrast = np.abs(gray.astype(np.float32)-np.median(border)).astype(np.uint8)
        _, binary = cv2.threshold(contrast,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours,key=cv2.contourArea)
        if cv2.contourArea(contour) < gray.size*self.min_area_fraction:
            return None
        x,y,w,h = cv2.boundingRect(contour)
        mask = np.zeros(gray.shape,dtype=np.uint8)
        cv2.drawContours(mask,[contour],-1,1,cv2.FILLED)
        return ROI((x,y,x+w,y+h),mask.astype(bool))


class YOLOROIExtractor(ROIExtractor):
    def __init__(self, weights: Path, confidence: float = .25):
        if not weights.is_file():
            raise FileNotFoundError(weights)
        if not 0 < confidence <= 1:
            raise ValueError('confidence must be in (0,1]')
        from ultralytics import YOLO  # optional; core experiments never require this
        self.model = YOLO(str(weights))
        if self.model.task != 'segment':
            raise ValueError('ROI extraction requires segmentation weights')
        self.confidence = confidence

    def extract(self, image: np.ndarray) -> ROI | None:
        prediction = self.model.predict(np.ascontiguousarray(image[:,:,::-1]),
                                        conf=self.confidence,retina_masks=True,verbose=False)[0]
        if prediction.masks is None or prediction.boxes is None or len(prediction.boxes) == 0:
            return None
        masks = prediction.masks.data.cpu().numpy()
        # Fixed selection rule: largest detected instance, not the best anomaly outcome.
        index = int(np.argmax([mask.sum() for mask in masks]))
        mask = cv2.resize(masks[index],(image.shape[1],image.shape[0]),interpolation=cv2.INTER_NEAREST) > .5
        ys,xs = np.where(mask)
        if not len(xs):
            return None
        return ROI((int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1),mask)


def overlay(image: np.ndarray, roi: ROI) -> np.ndarray:
    result = image.copy()
    result[roi.mask] = (.65*result[roi.mask]+.35*np.array([0,255,0])).astype(np.uint8)
    x1,y1,x2,y2 = roi.bbox
    cv2.rectangle(result,(x1,y1),(x2-1,y2-1),(255,0,0),2)
    return result
