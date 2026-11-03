import time

import pytest
from cryptography.fernet import Fernet

from herald_server.crypto import BadSecret, SecretBox

KEY = Fernet.generate_key().decode()


def test_seal_and_open_round_trip():
    box = SecretBox(KEY)
    assert box.open(box.seal({"refresh_token": "r1"})) == {"refresh_token": "r1"}


def test_tampered_token_is_rejected():
    box = SecretBox(KEY)
    token = box.seal({"a": 1})
    with pytest.raises(BadSecret):
        box.open(token[:-4] + "AAAA")


def test_other_key_is_rejected():
    with pytest.raises(BadSecret):
        SecretBox(Fernet.generate_key().decode()).open(SecretBox(KEY).seal({"a": 1}))


def test_expired_token_is_rejected():
    box = SecretBox(KEY)
    token = box.seal({"a": 1})
    with pytest.raises(BadSecret):
        box.open(token, max_age=600, now=int(time.time()) + 601)
