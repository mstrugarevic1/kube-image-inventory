from app.registry import compare_tags

def test_identical_tags_are_current():
    assert compare_tags("1.2.3", "1.2.3") == "current"

def test_older_tag_is_outdated():
    assert compare_tags("1.2.2", "1.2.3") == "outdated"

def test_non_semver_tag_is_unknown():
    assert compare_tags("abc", "1.2.3") == "unknown"

def test_newer_local_tag_is_unknown():
    assert compare_tags("1.2.4", "1.2.3") == "unknown"
