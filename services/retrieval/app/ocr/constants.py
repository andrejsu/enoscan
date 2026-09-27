SEARCH_TEXT_MIN_CONFIDENCE = 40

OCR_CROP_BOX = (0.25, 0.15, 0.75, 0.90)
OCR_CROP_MIN_ASPECT = 0.5
OCR_CROP_MIN_SIDE = 800
OCR_CROP_MIN_WORDS = 3

FIELD_LINE_MIN_CONFIDENCE = 60

HOMOGLYPH_MIN_LETTERS = 3

ABV_MIN = 1
ABV_MAX = 30

UNCOMMON_TOKEN_WEIGHT = 2

ALIAS_MIN_COUNT = 2
ALIAS_MIN_SHARE = 0.3
ALIAS_MIN_SIMILARITY = 0.75

CATEGORY_SYNONYMS = {
    **dict.fromkeys(("rose", "roze", "rosato", "rosado", "blush"), "Розовое"),
    **dict.fromkeys(("blanc", "bianco", "blanco", "white", "weiss", "byanko"), "Белое"),
    **dict.fromkeys(("rouge", "rosso", "tinto", "red", "rot", "ruzh"), "Красное"),
    **dict.fromkeys(("orange", "oranzh"), "Оранжевое"),
}

CLOSED_VOCABULARY_FIELDS = ("name", "winery", "grape_varieties", "category", "region")
WINERY_SHARED_FIELDS = ("name", "grape_varieties")
WINERY_SPENDS_WORDS_AT = 0.5
# Once the winery is read, other wineries' names count for this share of their score.
OTHER_WINERY_NAME_FACTOR = 0.5
RANKING_CANDIDATES = 50
