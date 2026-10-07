from app.services.categorization import categorize_document


def test_longer_vendor_pattern_wins():
    assert categorize_document("Galp Energia SA", None)[0] == "utilities"
    assert categorize_document("Galp Posto 123", None)[0] == "fuel"


def test_patterns_match_whole_words_only():
    assert categorize_document("Merenda Feliz", None)[0] == "other"
    assert categorize_document("Rinaldi Lda", None)[0] == "other"
