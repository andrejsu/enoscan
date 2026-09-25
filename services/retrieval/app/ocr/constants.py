SEARCH_TEXT_MIN_CONFIDENCE = 40

# OCR reads the middle of a phone photo first: at a shelf the neighbours'
# labels otherwise mix in («МУСКАТ … КРАСНОГО» of the next bottle), and the
# detector sees the label larger. (left, top, right, bottom) fractions.
# Narrow frames (a bottle cutout, width/height below the ratio) are already
# the bottle, so only their height is cropped. Measured 2026-09-25 on the 10
# labelled photos: the Massandra shelf photo and Anima read their names only
# in the crop, the rest read as before; OCR 1-3 s instead of 2-9 s.
OCR_CROP_BOX = (0.25, 0.15, 0.75, 0.90)
OCR_CROP_MIN_ASPECT = 0.5
# Smaller frames are already a close-up of the label (the 447 px Yaiyla
# photo lost «KOKUR» to the crop): they are read whole. A 960 px photo
# still gains from the crop (Anima: «ANMA» whole, «ANIMA» cropped).
OCR_CROP_MIN_SIDE = 800
# Fewer words than this in the crop: the label is elsewhere, read the full frame.
OCR_CROP_MIN_WORDS = 3

FIELD_LINE_MIN_CONFIDENCE = 60

HOMOGLYPH_MIN_LETTERS = 3

ABV_MIN = 1
ABV_MAX = 30

MIN_TOKEN_LENGTH = 3
STOP_WORDS = frozenset({
    "beloe", "butylka", "etiketka", "igristoe", "krasnoe", "rozovoe", "suhoe",
    "vino", "wine", "winery",
})

FUZZY_MIN_LENGTH = 5
FUZZY_MAX_LENGTH_GAP = 2
PREFIX_MIN_LENGTH = 6
PREFIX_SIMILARITY = 0.9
TOKEN_MATCH_SIMILARITY = 0.82
UNCOMMON_TOKEN_WEIGHT = 2

ALIAS_MIN_COUNT = 2
ALIAS_MIN_SHARE = 0.3
ALIAS_MIN_SIMILARITY = 0.75

# Label words (as raw_tokens spells them) that name a catalog category without
# sharing its spelling: "ROSE" transliterates to a token too far from "Розовое".
CATEGORY_SYNONYMS = {
    **dict.fromkeys(("rose", "roze", "rosato", "rosado", "blush"), "Розовое"),
    **dict.fromkeys(("blanc", "bianco", "blanco", "white", "weiss", "byanko"), "Белое"),
    **dict.fromkeys(("rouge", "rosso", "tinto", "red", "rot", "ruzh"), "Красное"),
    "orange": "Оранжевое",
}

CLOSED_VOCABULARY_FIELDS = ("name", "winery", "grape_varieties", "category", "region")
WINERY_SHARED_FIELDS = ("name", "grape_varieties")
WINERY_SPENDS_WORDS_AT = 0.5
RANKING_CANDIDATES = 50
