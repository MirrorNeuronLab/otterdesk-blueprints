import pytest

from cctv_operator.payloads.domain.mobileclip import MobileCLIPEncoder


def test_encoder_import_and_construction_do_not_load_or_download(tmp_path):
    encoder = MobileCLIPEncoder(tmp_path / "missing.pt")
    assert encoder._backend is None
    with pytest.raises(RuntimeError, match="not prepared"):
        encoder._load()


def test_text_cache_bounds_and_copy_isolation():
    encoder = MobileCLIPEncoder("unused")
    encoder._texts['query'] = [1., 0.]
    returned = encoder.encode_text('query')
    returned[0] = 0
    assert encoder.encode_text('query') == [1., 0.]
    with pytest.raises(ValueError):
        encoder.encode_text('x' * 1001)
