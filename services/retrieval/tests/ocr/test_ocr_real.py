from importlib.util import find_spec
from pathlib import Path

import pytest

from app.catalog import Wine
from app.image_features import decode_image
from app.label_fields import RetrievalFields
from app.ocr.retriever import OcrRetriever
from app.ocr.vocabulary import FieldVocabulary
from app.ranking import rank


pytestmark = pytest.mark.skipif(find_spec("rapidocr") is None, reason="rapidocr is not installed")
FIXTURES = Path(__file__).parents[1] / "fixtures"
WINES = [
    Wine("balaklava-muskat-beloe-polusladkoe", "Балаклава Мускат белое полусладкое", "Золотая Балка",
         category="Белое", region="Крым", grape_varieties=("Мускат Белый",)),
    Wine("perovskih_polusuhoe_krasnoe", "Полусухое Красное", "Усадьба Перовских",
         category="Красное", region="Крым", grape_varieties=("Мурведр", "Пино Нуар")),
    Wine("perovskih_polusladkoe_krasnoe", "Полусладкое Красное", "Усадьба Перовских",
         category="Красное", region="Крым", grape_varieties=("Мерло",)),
] + [Wine(f"decoy-{i}", f"Вино Decoy{i} Sort{i}", f"Winery{i}", category="Белое", region="Кубань")
     for i in range(6)]


def _fields(name: str) -> RetrievalFields:
    retriever = OcrRetriever(FieldVocabulary(WINES))
    return retriever.extract(decode_image((FIXTURES / name).read_bytes()))


def test_readable_label_yields_the_wine_name():
    fields = _fields("balaklava-muskat-beloe-polusladkoe.webp")
    assert fields.name and fields.name[0].value == "Балаклава Мускат белое полусладкое"
    assert rank(fields, RetrievalFields(), WINES).slug == "balaklava-muskat-beloe-polusladkoe"


def test_patterned_label_reads_the_winery_but_winery_alone_never_matches():
    fields = _fields("perovskih_polusuhoe_krasnoe.webp")
    assert fields.winery and fields.winery[0].value == "Усадьба Перовских"
    assert fields.category and fields.category[0].value == "Красное"
    assert rank(fields, RetrievalFields(), WINES).status == "not_found"
