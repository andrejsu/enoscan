"""Frozen DINOv2 global descriptor for wine-label instance retrieval.

Global embeddings are the ANN candidate-generation stage: cheap, robust to blur,
perspective and lighting, but not discriminative enough on their own (many wines
share a winery template). ``index.py`` reranks the shortlist this produces with
SIFT + RANSAC geometric verification, and ``service.py`` folds OCR text evidence
in on top — see ``SearchService.search`` for how the three signals combine.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from .download_model import MODEL_SHA256


MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
EMBEDDING_DIM = 384
REFERENCE_VISUAL_SIZE = 512
EMBEDDING_MODEL = f"dinov2-small@{MODEL_SHA256[:12]}/label-prep-{REFERENCE_VISUAL_SIZE}"


def read_embedding_image(path: str) -> np.ndarray | None:
    """Read catalog art with transparent pixels composited onto white."""
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        return np.rint(image[:, :, :3] * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    return image[:, :, :3]


class Dinov2Encoder:
    def __init__(self, model_path: Path, *, threads: int = 4) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=["CPUExecutionProvider"])

    def encode(self, images: list[np.ndarray]) -> np.ndarray:
        if not images:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
        prepared = []
        for image in images:
            rgb = cv2.cvtColor(cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA),
                               cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            prepared.append(((rgb - MEAN) / STD).transpose(2, 0, 1))
        tokens = self.session.run(None, {"pixel_values": np.stack(prepared)})[0]
        vectors = tokens[:, 0].astype(np.float32)
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8)

    def encode_one(self, image: np.ndarray) -> np.ndarray:
        return self.encode([image])[0]
