from datetime import date

from medsync.pipeline.deduplicator import (
    PatientFields,
    assign_clusters,
    build_blocks,
    classify,
    exact,
    jaro_winkler,
    score_pair,
    soundex_block_key,
    token_overlap,
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


def _shaq(fhir_id="a", last="O'Neal", given="Shaq"):
    return PatientFields(fhir_id, last, given, date(1968, 3, 14), "male",
                         "482 Oakwood Drive", "62704")


def test_score_pair_identical_is_high():
    assert score_pair(_shaq("a"), _shaq("b")) > 6.0


def test_score_pair_name_variation_still_positive():
    # Same DOB/gender/address, given name typo -> should still score well above 0
    s = score_pair(_shaq("a", given="Shaq"), _shaq("b", given="Shaquille"))
    assert s > 0.0


def test_score_pair_different_people_is_low():
    kobe = PatientFields("c", "Bryant", "Kobe", date(1978, 8, 23), "male",
                         "8 Mamba Ln", "90001")
    assert score_pair(_shaq("a"), kobe) < 0.0


def test_classify_zones():
    assert classify(7.0, upper=6.0, lower=0.0) == "match"
    assert classify(3.0, upper=6.0, lower=0.0) == "possible"
    assert classify(-1.0, upper=6.0, lower=0.0) == "non-match"


def test_assign_clusters_unions_match_pairs():
    ids = ["a", "b", "c", "d"]
    clusters = assign_clusters(ids, [("a", "b"), ("b", "c")])
    assert clusters["a"] == clusters["b"] == clusters["c"]
    assert clusters["d"] != clusters["a"]  # singleton


def test_assign_clusters_deterministic_min_id():
    clusters = assign_clusters(["b", "a"], [("a", "b")])
    assert clusters["a"] == clusters["b"] == "a"  # min id is the cluster id


def test_build_blocks_groups_by_soundex_and_year():
    a = PatientFields("a", "O'Neal", "Shaq", date(1968, 3, 14), "male", "x", "1")
    b = PatientFields("b", "Oneal", "Shaquille", date(1968, 7, 1), "male", "x", "1")
    c = PatientFields("c", "Bryant", "Kobe", date(1978, 8, 23), "male", "y", "2")
    blocks = build_blocks([a, b, c])
    # a and b share Soundex(last)+birth_year -> same block; c separate
    key_ab = next(k for k, v in blocks.items() if any(p.fhir_id == "a" for p in v))
    assert {p.fhir_id for p in blocks[key_ab]} == {"a", "b"}
