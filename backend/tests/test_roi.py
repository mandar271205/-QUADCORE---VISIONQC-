"""ROI geometry and no-detection cases, independent of the anomaly detector."""
import numpy as np
import pytest
from app.services.ml.roi import OpenCVROIExtractor, overlay


def test_roi_crop_and_mask():
    image = np.zeros((80,100,3),dtype=np.uint8)
    image[20:60,30:70] = 255
    roi = OpenCVROIExtractor().extract(image)
    assert roi is not None and roi.bbox == (30,20,70,60)
    assert roi.crop(image).shape == (40,40,3)
    assert roi.mask.sum() == 1600
    assert overlay(image,roi).shape == image.shape


def test_no_roi_and_tiny_noise():
    extractor = OpenCVROIExtractor()
    assert extractor.extract(np.zeros((80,100,3),dtype=np.uint8)) is None
    image = np.zeros((80,100,3),dtype=np.uint8); image[20:22,30:32] = 255
    assert extractor.extract(image) is None
    with pytest.raises(ValueError):
        OpenCVROIExtractor(2)


def test_yolo_roi_uses_original_geometry_and_largest_instance():
    from types import SimpleNamespace
    from app.services.ml.roi import YOLOROIExtractor
    masks=np.zeros((2,80,120),dtype=np.float32)
    masks[0,1:5,2:8]=1;masks[1,17:60,30:85]=1
    class MaskData:
        def cpu(self):return self
        def numpy(self):return masks
    class Model:
        def predict(self,image,**kwargs):
            # Without retina_masks, letterbox padding can shift the crop.
            assert kwargs['retina_masks'] is True
            assert image.flags.c_contiguous and image[0,0].tolist()==[30,20,10]
            return [SimpleNamespace(masks=SimpleNamespace(data=MaskData()),boxes=[0,1])]
    extractor=YOLOROIExtractor.__new__(YOLOROIExtractor)
    extractor.model=Model();extractor.confidence=.25
    image=np.full((80,120,3),[10,20,30],dtype=np.uint8)
    roi=extractor.extract(image)
    assert roi.bbox==(30,17,85,60) and roi.crop(image).shape==(43,55,3)
