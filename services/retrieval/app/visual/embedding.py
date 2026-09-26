"""Frozen DINOv2 global descriptor for wine-label instance retrieval.

Global embeddings are the ANN candidate-generation stage: cheap, robust to blur,
perspective and lighting, but not discriminative enough on their own (many wines
share a winery template). ``app/sift_index.py`` reranks the shortlist this produces
with SIFT + RANSAC geometric verification — see ``VisualRetriever.search`` for how
the two signals combine; OCR text evidence is folded in later by app/search.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from .download_model import MODEL_SHA256


MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
REFERENCE_VISUAL_SIZE = 512
EMBEDDING_MODEL = f"dinov2-small@{MODEL_SHA256[:12]}/label-prep-{REFERENCE_VISUAL_SIZE}"


class Dinov2Encoder:
    def __init__(self, model_path: Path, *, threads: int = 4) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=["CPUExecutionProvider"])

    def encode(self, image: np.ndarray) -> np.ndarray:
        """The image's L2-normalized CLS token."""
        rgb = cv2.cvtColor(cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA),
                           cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        pixels = np.stack([((rgb - MEAN) / STD).transpose(2, 0, 1)])
        vectors = self.session.run(None, {"pixel_values": pixels})[0][:, 0].astype(np.float32)
        return (vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8))[0]
