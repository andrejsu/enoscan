from ..catalog.repository import current_dataset_version, load_references
from ..image_features import decode_reference, extract_features
from ..index_store import find_build, publish_index
from ..sift_index import IndexedReference
from ..storage import IMAGES_BUCKET, ObjectStore
from .config import SIFT_INDEX_KIND, load_settings


def main() -> None:
    settings = load_settings()
    version = current_dataset_version(settings.database_url)
    if find_build(settings.database_url, SIFT_INDEX_KIND, version) is not None:
        print(f"Retrieval index {SIFT_INDEX_KIND} for dataset {version} already built.")
        return

    store = ObjectStore()
    references = load_references(settings.database_url)
    print(f"Indexing {len(references)} mapped references for dataset {version}.")

    indexed_references: list[IndexedReference] = []
    features = []
    skipped = 0
    for position, reference in enumerate(references, start=1):
        try:
            image = decode_reference(store.get_bytes(IMAGES_BUCKET, reference.object_key), reference.object_key)
            item_features = extract_features(image, max_side=1200, feature_count=700)
        except ValueError as error:
            print(error)
            skipped += 1
            continue
        if len(item_features.descriptors) < 8:
            skipped += 1
            continue

        indexed_references.append(IndexedReference(reference.wine, reference.image_sha256))
        features.append(item_features)
        if position % 100 == 0:
            print(f"Processed {position}/{len(references)} references.", flush=True)

    if not features:
        raise SystemExit("No usable reference images were indexed.")
    build = publish_index(store, settings.database_url, SIFT_INDEX_KIND, version, indexed_references, features)
    print(f"Saved {build.reference_count} references to {build.object_key}; skipped {skipped}.")


if __name__ == "__main__":
    main()
