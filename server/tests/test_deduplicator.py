from medsync.pipeline.deduplicator import (
    soundex_block_key, jaro_winkler, token_overlap, exact,
)


def test_soundex_block_key_groups_similar_surnames():
    # Same Soundex + same birth year -> same block
    assert soundex_block_key("Oneal", 1968) == soundex_block_key("O'Neal", 1968)
    assert soundex_block_key("Oneal", 1968) != soundex_block_key("Oneal", 1970)


def test_soundex_block_key_handles_missing():
    assert soundex_block_key(None, None) == "____"  # sentinel, still a string


def test_jaro_winkler_prefix_weighted():
    assert jaro_winkler("Shaquille", "Shaquile") > 0.9
    assert jaro_winkler("Shaq", "Kobe") < 0.6
    assert jaro_winkler(None, "Shaq") == 0.0


def test_token_overlap_ratio():
    assert token_overlap("482 Oakwood Drive", "482 Oakwood Dr") >= 0.5
    assert token_overlap("482 Oakwood Drive", "77 Birch Lane") == 0.0
    assert token_overlap(None, "x") == 0.0


def test_exact_match():
    assert exact("M", "M") == 1.0
    assert exact("M", "F") == 0.0
    assert exact(None, None) == 0.0  # unknown != agreement
