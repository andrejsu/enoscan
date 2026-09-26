"""Build the visual retriever's own index — a separate object from the
baseline's (app/baseline/build_index.py), which this module never touches.

Each reference is normalized once via preprocessing.prepare_reference_image
(no SAM: alpha-channel/bottle-crop heuristic, fast enough for the whole
catalog in minutes) and that same crop feeds both the SIFT descriptors and the
DINOv2 embedding. Embeddings are stored in pgvector keyed by image sha256 and
model, so only images without an embedding for the current model are encoded.
"""

from pathlib import Path

import cv2
import numpy as np

from ..catalog.repository import current_dataset_version, load_references
from ..image_features import decode_reference, extract_features
from ..index_store import find_build, publish_index
from ..sift_index import IndexedReference
from ..storage import IMAGES_BUCKET, ObjectStore
from . import download_model
from .config import RETRIEVER_INDEX_KIND, load_retriever_settings
from .embedding import EMBEDDING_MODEL, REFERENCE_VISUAL_SIZE, Dinov2Encoder
from .embedding_store import EmbeddingStore
from .preprocessing import Config as LabelConfig, prepare_reference_image


EMBEDDING_BATCH = 100


def main() -> None:
    settings = load_retriever_settings()
    version = current_dataset_version(settings.database_url)
    if find_build(settings.database_url, RETRIEVER_INDEX_KIND, version) is not None:
        print(f"Retriever index {RETRIEVER_INDEX_KIND} for dataset {version} already built.")
        return

    download_model.main()
    encoder = Dinov2Encoder(Path(settings.model_path), threads=8)
    label_config = LabelConfig(visual_size=REFERENCE_VISUAL_SIZE)
    store = ObjectStore()
    embeddings = EmbeddingStore(settings.database_url, EMBEDDING_MODEL)

    references = load_references(settings.database_url)
    missing = embeddings.missing(reference.image_sha256 for reference in references)
    print(f"Indexing {len(references)} references for dataset {version}; "
          f"{len(missing)} need new embeddings ({EMBEDDING_MODEL}).", flush=True)

    indexed_references: list[IndexedReference] = []
    features = []
    pending: list[tuple[str, np.ndarray]] = []
    encoded = 0
    for position, reference in enumerate(references, start=1):
        try:
            source = decode_reference(store.get_bytes(IMAGES_BUCKET, reference.object_key), reference.object_key,
                                      cv2.IMREAD_UNCHANGED)
            normalized = prepare_reference_image(source, config=label_config)
            item_features = extract_features(normalized, max_side=1200, feature_count=700)
            if reference.image_sha256 in missing:
                pending.append((reference.image_sha256, encoder.encode(normalized)))
                missing.discard(reference.image_sha256)
                encoded += 1
        except (ValueError, RuntimeError) as error:
            print(f"{reference.object_key}: {error}")
            continue
        if len(pending) >= EMBEDDING_BATCH:
            embeddings.upsert_many(pending)
            pending = []
        if len(item_features.descriptors) < 8:
            continue

        indexed_references.append(IndexedReference(reference.wine, reference.image_sha256))
        features.append(item_features)
        if position % 100 == 0:
            print(f"Processed {position}/{len(references)} references.", flush=True)
    embeddings.upsert_many(pending)

    unembedded = embeddings.missing(item.image_sha256 for item in indexed_references)
    kept = [(item, feature) for item, feature in zip(indexed_references, features, strict=True)
            if item.image_sha256 not in unembedded]
    indexed_references = [item for item, _ in kept]
    features = [feature for _, feature in kept]
    embeddings.close()

    if not features:
        raise SystemExit("No usable reference images were indexed.")
    build = publish_index(store, settings.database_url, RETRIEVER_INDEX_KIND, version, indexed_references, features)
    print(f"Saved {build.reference_count} references to {build.object_key}; encoded {encoded} new embeddings.")


if __name__ == "__main__":
    main()
