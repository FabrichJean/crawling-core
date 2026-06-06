from urllib.parse import parse_qs

from crawling_core.codec import AesCfbCodec, NoopCodec


def test_noop_codec_roundtrips_dict():
    codec = NoopCodec()
    payload = {"a": 1, "b": "two"}
    assert codec.decode_response(codec.encode_request(payload)) == payload


def test_noop_codec_decodes_json_string():
    codec = NoopCodec()
    assert NoopCodec().decode_response('{"x": 1}') == {"x": 1}
    assert codec.decode_response("not json") is None


def test_aes_cfb_codec_roundtrips_through_data_field():
    codec = AesCfbCodec(key=b"0123456789abcdef", iv=b"abcdef0123456789", client="pwa")
    payload = {"hello": "world", "page": 1}

    envelope = codec.encode_request(payload)
    assert envelope.startswith("client=pwa&timestamp=")

    encrypted_hex = parse_qs(envelope)["data"][0]
    assert codec.decode_response(encrypted_hex) == payload
    assert codec.decode_response({"data": encrypted_hex}) == payload


def test_aes_cfb_codec_returns_none_on_garbage():
    codec = AesCfbCodec(key=b"0123456789abcdef", iv=b"abcdef0123456789")
    assert codec.decode_response("not-hex-data") is None
    assert codec.decode_response(None) is None
