"""Build the retriever's own index — separate file, separate process from
app/build_index.py (which builds the existing OCR-driven service's index and
is untouched by this module).

Each reference is normalized once via label_normalize.prepare_reference (no
SAM: alpha-channel/bottle-crop heuristic, fast enough for the whole catalog
in minutes) and that same crop feeds both the SIFT descriptors and the
DINOv2 embedding stored for it.
"""

from pathlib import Path

import numpy as np

from . import download_model
from .catalog import load_catalog, resolve_references
from .embedding import Dinov2Encoder
from .image_features import extract_features
from .label_normalize import Config as LabelConfig, prepare_reference
from .retriever_config import load_retriever_settings
from .retriever_index import IndexedReference, save_index


def main() -> None:
    settings = load_retriever_settings()
    output = Path(settings.index_path)
    if output.exists():
        print(f"Retriever index already exists: {output}")
        return

    download_model.main()
    encoder = Dinov2Encoder(Path(settings.model_path), threads=8)
    label_config = LabelConfig(visual_size=512)

    wines, media = load_catalog(settings.database_url)
    resolved = resolve_references(wines, media)
    print(f"Resolved {len(resolved)} references for {len(wines)} catalog wines.")

    indexed_references: list[IndexedReference] = []
    features = []
    vectors: list[np.ndarray] = []
    uploads = Path(settings.dataset_root) / "uploads"
    for position, reference in enumerate(resolved, start=1):
        path = uploads / reference.relative_path
        try:
            normalized = prepare_reference(str(path), config=label_config)
            item_features = extract_features(normalized, max_side=1200, feature_count=700)
        except (ValueError, RuntimeError) as error:
            print(f"{path}: {error}")
            continue
        if len(item_features.descriptors) < 8:
            continue

        indexed_references.append(IndexedReference(
            wine=reference.wine,
            relative_path=reference.relative_path,
            mapping_kind=reference.mapping_kind,
            mapping_score=reference.mapping_score,
        ))
        features.append(item_features)
        vectors.append(encoder.encode_one(normalized))
        if position % 100 == 0:
            print(f"Processed {position}/{len(resolved)} references.")

    if not features:
        raise SystemExit("No usable reference images were indexed.")
    save_index(settings.index_path, indexed_references, features, embeddings=np.stack(vectors))
    print(f"Saved {len(features)} references to {settings.index_path}.")


if __name__ == "__main__":
    main()
