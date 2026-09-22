from io import BytesIO
from pathlib import Path

from PIL import Image

from importer.archive import classify, strapi_path_of
from importer.images import decode_and_preview, original_key, preview_key
from importer.versioning import DatasetFingerprint, EMPTY_SHA256, archive_sha256, optional_file_sha256


def encode(image: Image.Image, image_format: str, **options: object) -> bytes:
    output = BytesIO()
    image.save(output, format=image_format, **options)
    return output.getvalue()


def test_dataset_version_changes_with_every_input() -> None:
    base = DatasetFingerprint("c", "a", "o")
    variants = [
        DatasetFingerprint("c2", "a", "o"),
        DatasetFingerprint("c", "a2", "o"),
        DatasetFingerprint("c", "a", "o2"),
        DatasetFingerprint("c", "a", "o", mapping_algo_version="m2"),
        DatasetFingerprint("c", "a", "o", preview_version="p2"),
    ]

    assert base.dataset_version == DatasetFingerprint("c", "a", "o").dataset_version
    assert len({base.dataset_version, *(item.dataset_version for item in variants)}) == 6


def test_archive_hash_depends_on_volume_order(tmp_path: Path) -> None:
    first = tmp_path / "part1"
    second = tmp_path / "part2"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    assert archive_sha256([first, second]) != archive_sha256([second, first])
    assert optional_file_sha256(tmp_path / "missing.csv") == EMPTY_SHA256


def test_preview_fits_box_and_keeps_alpha() -> None:
    source = Image.new("RGBA", (1000, 3000), (200, 0, 0, 0))

    decoded = decode_and_preview(encode(source, "PNG"))

    with Image.open(BytesIO(decoded.preview)) as preview:
        assert preview.format == "WEBP"
        assert preview.width <= 400 and preview.height <= 600
        assert preview.mode == "RGBA"
    assert (decoded.width, decoded.height, decoded.mime, decoded.extension) == (1000, 3000, "image/png", ".png")


def test_exif_orientation_is_applied() -> None:
    source = Image.new("RGB", (300, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6

    decoded = decode_and_preview(encode(source, "JPEG", exif=exif.tobytes()))

    assert (decoded.width, decoded.height) == (100, 300)
    assert decoded.extension == ".jpg"


def test_object_keys_are_content_addressed() -> None:
    sha = "ab" + "0" * 62

    assert original_key(sha, ".webp") == f"originals/ab/{sha}.webp"
    assert preview_key(sha).startswith("previews/webp-400x600-q80-v1/ab/")


def test_archive_member_classification() -> None:
    prefix = "prod-svoe-vino-strapi/prod-svoe-vino/strapi/uploads/"

    assert strapi_path_of(prefix + "a/b.webp") == "a/b.webp"
    assert classify(prefix + "label_0123456789.WEBP") == "original"
    assert classify(prefix + "thumbnail_label.webp") == "derivative"
    assert classify(prefix + "map.geojson") == "unsupported_extension"
    assert classify("other/label.webp") == "outside_uploads"
