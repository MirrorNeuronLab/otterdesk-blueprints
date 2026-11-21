from names import normalize_name


def test_name():
    assert normalize_name(" Ada ") == "Ada"
