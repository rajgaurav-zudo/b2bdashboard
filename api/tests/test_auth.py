"""Token verification and the allow-list.

Supabase signs with ES256 against a published JWKS, so these tests mint tokens
with their own key pair and point the verifier at it. That exercises the real
decode path -- signature, audience, issuer, expiry -- rather than a stub of it.

The case that matters most is the valid-but-unwelcome one: a Supabase project
takes public sign-ups by default, so a correctly signed token proves only that
someone found the sign-up form.
"""
import sys
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, "/srv/api")

from app import auth  # noqa: E402
from app.config import settings  # noqa: E402

PROJECT = "https://project.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", PROJECT)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_allowed_emails", ["owner@example.com"])
    monkeypatch.setattr(settings, "auth_allowed_domains", ["edvoy.com"])

    class _Signing:
        key = KEY.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Signing()

    monkeypatch.setattr(auth, "_jwk_client", _Client())
    yield
    auth._jwk_client = None


def token(**overrides) -> str:
    claims = {
        "sub": "user-uuid",
        "email": "someone@edvoy.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": f"{PROJECT}/auth/v1",
        "exp": int(time.time()) + 3600,
        **overrides,
    }
    return jwt.encode(claims, KEY, algorithm="ES256")


def test_a_properly_signed_token_from_an_allowed_domain_is_accepted():
    user = auth.verify(token())
    assert user.email == "someone@edvoy.com"
    assert user.sub == "user-uuid"


def test_an_explicitly_listed_address_is_accepted_outside_the_domains():
    assert auth.verify(token(email="owner@example.com")).email == "owner@example.com"


def test_a_valid_token_from_an_unlisted_address_is_403_not_401():
    """The signature is fine and the account is real -- this person is simply not
    permitted. 401 would tell the browser to try authenticating again, which
    cannot help and produces a sign-in loop."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token(email="stranger@gmail.com"))
    assert err.value.status_code == 403


def test_signup_without_an_email_claim_is_refused():
    """Anonymous sign-ins carry no email, so nothing can be matched against."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token(email=""))
    assert err.value.status_code == 403


def test_expired_tokens_are_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token(exp=int(time.time()) - 10))
    assert err.value.status_code == 401
    assert "expired" in str(err.value.detail)


def test_a_token_for_another_project_is_refused():
    """Same algorithm, same shape, different issuer -- must not be accepted."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token(iss="https://someone-else.supabase.co/auth/v1"))
    assert err.value.status_code == 401


def test_a_token_for_a_different_audience_is_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token(aud="anon"))
    assert err.value.status_code == 401


def test_a_token_signed_by_a_different_key_is_refused():
    other = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(
        {"sub": "x", "email": "someone@edvoy.com", "aud": "authenticated",
         "iss": f"{PROJECT}/auth/v1", "exp": int(time.time()) + 3600},
        other, algorithm="ES256",
    )
    with pytest.raises(auth.AuthError) as err:
        auth.verify(forged)
    assert err.value.status_code == 401


def test_a_token_with_no_expiry_is_refused():
    """`require: exp` matters -- a token that never expires cannot be revoked by
    waiting, and Supabase always sets one."""
    claims = {"sub": "x", "email": "someone@edvoy.com", "aud": "authenticated",
              "iss": f"{PROJECT}/auth/v1"}
    with pytest.raises(auth.AuthError):
        auth.verify(jwt.encode(claims, KEY, algorithm="ES256"))


@pytest.mark.parametrize("email,ok", [
    ("Someone@Edvoy.com", True),        # case folded on both sides
    ("  someone@edvoy.com  ", True),    # trimmed
    ("someone@notedvoy.com", False),    # not a suffix match: the domain is exact
    ("someone@edvoy.com.attacker.io", False),
    ("edvoy.com", False),               # a bare domain is not an address
    ("", False),
])
def test_allow_list_matching(email, ok):
    assert auth._allowed(email) is ok


def test_preflight_refuses_auth_without_a_list(monkeypatch):
    """Requiring auth but admitting everyone who can sign up is the worst of both:
    it looks protected."""
    monkeypatch.setattr(settings, "auth_allowed_emails", [])
    monkeypatch.setattr(settings, "auth_allowed_domains", [])
    assert any("ALLOWED" in p for p in auth.preflight())


def test_preflight_refuses_auth_without_a_project_url(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    assert any("SUPABASE_URL" in p for p in auth.preflight())


def test_preflight_is_quiet_when_auth_is_off(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "auth_allowed_emails", [])
    monkeypatch.setattr(settings, "auth_allowed_domains", [])
    assert auth.preflight() == []


def test_audit_actor_prefers_the_signed_in_identity():
    assert auth.audit_actor(auth.User("s", "a@edvoy.com", "authenticated")) == "a@edvoy.com"
    assert auth.audit_actor(None) is None
