SEARCH_TEXT_MIN_CONFIDENCE = 40
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

CLOSED_VOCABULARY_FIELDS = ("name", "winery", "grape_varieties", "category", "color", "region")
WINERY_SHARED_FIELDS = ("name", "grape_varieties")
WINERY_SPENDS_WORDS_AT = 0.5
RANKING_CANDIDATES = 50
