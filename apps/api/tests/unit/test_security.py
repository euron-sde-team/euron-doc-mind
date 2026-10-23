import uuid
from datetime import timedelta

import jwt
import pytest

from docmind.core.errors import UnauthorizedError, UnprocessableError
from docmind.core.security import (
    decode_session,
    generate_api_key,
    hash_password,
    issue_session,
    parse_api_key,
    validate_password,
    verify_api_key_secret,
    verify_password,
)

SECRET = "test-only-session-secret-0123456789abcdef"


def test_password_hashing_round_trip_and_unknown_user() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong horse battery")
    assert not verify_password(None, "correct horse battery")


@pytest.mark.parametrize("password", ["short", "aaaaaaaaaaaa", "x" * 300])
def test_password_policy_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(UnprocessableError):
        validate_password(password)


def test_password_cannot_be_the_email() -> None:
    with pytest.raises(UnprocessableError):
        validate_password("ava@northwind.example", email="Ava@Northwind.example")


def test_session_round_trip() -> None:
    user_id = uuid.uuid4()
    token, claims = issue_session(user_id, 3, secret=SECRET, ttl=timedelta(hours=1))
    decoded = decode_session(token, secret=SECRET)
    assert decoded.user_id == user_id
    assert decoded.session_version == 3
    assert decoded.jti == claims.jti


def test_sessions_reject_tampering_expiry_and_foreign_audiences() -> None:
    token, _ = issue_session(uuid.uuid4(), 1, secret=SECRET, ttl=timedelta(hours=1))
    with pytest.raises(UnauthorizedError):
        decode_session(token, secret=SECRET + "x")
    expired, _ = issue_session(uuid.uuid4(), 1, secret=SECRET, ttl=timedelta(seconds=-5))
    with pytest.raises(UnauthorizedError):
        decode_session(expired, secret=SECRET)
    foreign = jwt.encode({"sub": str(uuid.uuid4()), "aud": "other", "iss": "docmind"}, SECRET, algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        decode_session(foreign, secret=SECRET)


def test_api_keys_are_parsed_and_verified_with_the_pepper() -> None:
    key = generate_api_key("pepper-one")
    parsed = parse_api_key(key.plaintext)
    assert parsed is not None and parsed[0] == key.prefix
    assert verify_api_key_secret(parsed[1], key.secret_hash, "pepper-one")
    assert not verify_api_key_secret(parsed[1], key.secret_hash, "pepper-two")
    assert parse_api_key("dmk_tooshort") is None
    assert parse_api_key(key.plaintext + "x") is None
