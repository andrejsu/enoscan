from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ImageFeatures:
    keypoints: np.ndarray
    descriptors: np.ndarray


def decode_image(content: bytes) -> np.ndarray:
    encoded = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Файл не удалось декодировать как изображение.")
    return image


def decode_reference(content: bytes, name: str) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode reference image: {name}")
    return image


def extract_features(image: np.ndarray, *, max_side: int, feature_count: int) -> ImageFeatures:
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    sift = cv2.SIFT_create(nfeatures=feature_count, contrastThreshold=0.025)
    keypoints, descriptors = sift.detectAndCompute(gray, None)
    if descriptors is None or len(keypoints) < 2:
        return ImageFeatures(
            keypoints=np.empty((0, 2), dtype=np.float32),
            descriptors=np.empty((0, 128), dtype=np.float32),
        )

    points = np.array([point.pt for point in keypoints], dtype=np.float32)
    descriptors = _root_sift(descriptors)
    return ImageFeatures(keypoints=points, descriptors=descriptors)


def _root_sift(descriptors: np.ndarray) -> np.ndarray:
    descriptors = descriptors.astype(np.float32, copy=False)
    descriptors /= np.maximum(descriptors.sum(axis=1, keepdims=True), 1e-7)
    return np.sqrt(descriptors)

