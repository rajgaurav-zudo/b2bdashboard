"""Google sign-in, the domain check, and the API's own session tokens.

Google signs ID tokens with RS256 against a published JWKS, so these tests mint
tokens with their own key pair and point the verifier at it. That exercises the
real decode path -- signature, audience, issuer, expiry -- rather than a stub.

The case that matters most is the valid-but-unwelcome one: anyone with a Google
account can get a correctly signed token for this client, so a good signature
proves only that someone clicked the button.
"""
import sys
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, "/srv/api")

from app import auth  # noqa: E402
from app.config import settings  # noqa: E402

CLIENT_ID = "1234-abc.apps.googleusercontent.com"
SECRET = "s" * 48
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    monkeypatch.setattr(settings, "auth_session_hours", 12)
    monkeypatch.setattr(settings, "auth_allowed_domains", ["edvoy.com"])
    monkeypatch.setattr(settings, "auth_owner_email", "owner@edvoy.com")
    # everyone is on the user list here; test_users.py covers the list itself
    monkeypatch.setattr(auth.users, "get", lambda email: {"email": email, "name": "", "role": "member",
                                                          "active": True})
    monkeypatch.setattr(auth.users, "signed_in", lambda email, name: None)

    class _Signing:
        key = KEY.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Signing()

    monkeypatch.setattr(auth, "_jwk_client", _Client())
    yield
    auth._jwk_client = None


def google_token(key=KEY, drop=(), **overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1093847",
        "email": "someone@edvoy.com",
        "email_verified": True,
        "hd": "edvoy.com",
        "name": "Some One",
        "exp": int(time.time()) + 3600,
        **overrides,
    }
    for claim in drop:
        del claims[claim]
    return jwt.encode(claims, key, algorithm="RS256")


# --- the Google ID token ------------------------------------------------------

def test_a_workspace_account_in_the_domain_is_accepted():
    user = auth.verify_google(google_token())
    assert (user.email, user.sub, user.name) == ("someone@edvoy.com", "1093847", "Some One")


def test_both_spellings_of_googles_issuer_are_accepted():
    assert auth.verify_google(google_token(iss="accounts.google.com")).email == "someone@edvoy.com"


def test_an_account_outside_the_domain_is_403_not_401():
    """The signature is fine and the account is real -- this person is simply not
    one of ours. 401 would tell the browser to try authenticating again, which
    cannot help."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(email="stranger@gmail.com", drop=["hd"]))
    assert err.value.status_code == 403
    assert "@edvoy.com" in str(err.value.detail)


def test_another_workspace_is_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(email="someone@other.com", hd="other.com"))
    assert err.value.status_code == 403


def test_a_personal_account_under_a_company_address_is_refused():
    """A consumer Google account can be registered with any address its owner can
    read mail at. It has the right email and no `hd`: only accounts the Workspace
    itself manages are let in."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(drop=["hd"]))
    assert err.value.status_code == 403


def test_the_address_must_match_as_well_as_the_workspace():
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(email="someone@gmail.com"))
    assert err.value.status_code == 403


def test_an_unverified_address_is_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(email_verified=False))
    assert err.value.status_code == 403


def test_a_token_issued_to_another_app_is_refused():
    """Signed by Google, for a real edvoy.com account -- but for someone else's
    client. Accepting it would let any site with a Google button sign in here."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(aud="someone-else.apps.googleusercontent.com"))
    assert err.value.status_code == 401


def test_a_token_from_another_issuer_is_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(iss="https://accounts.example.com"))
    assert err.value.status_code == 401


def test_an_expired_google_token_is_refused():
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(exp=int(time.time()) - 10))
    assert err.value.status_code == 401
    assert "expired" in str(err.value.detail)


def test_a_token_signed_by_a_different_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(google_token(key=other))
    assert err.value.status_code == 401


def test_a_session_token_cannot_be_replayed_as_a_google_sign_in():
    token, _ = auth.issue_session(auth.User("s", "someone@edvoy.com"))
    with pytest.raises(auth.AuthError) as err:
        auth.verify_google(token)
    assert err.value.status_code == 401


# --- the session token --------------------------------------------------------

def test_a_session_round_trips():
    token, expires = auth.issue_session(auth.User("1093847", "someone@edvoy.com", "Some One"))
    user = auth.verify(token)
    assert (user.email, user.sub, user.name) == ("someone@edvoy.com", "1093847", "Some One")
    assert expires == pytest.approx(time.time() + 12 * 3600, abs=5)


def test_a_google_token_is_not_a_session():
    """The exchange is the only way in: the domain check lives there."""
    with pytest.raises(auth.AuthError) as err:
        auth.verify(google_token())
    assert err.value.status_code == 401


def test_a_session_signed_with_another_secret_is_refused():
    forged = jwt.encode(
        {"iss": auth.SESSION_ISSUER, "sub": "x", "email": "someone@edvoy.com",
         "exp": int(time.time()) + 3600},
        "x" * 48, algorithm="HS256",
    )
    with pytest.raises(auth.AuthError) as err:
        auth.verify(forged)
    assert err.value.status_code == 401


def test_an_expired_session_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "auth_session_hours", -1)
    token, _ = auth.issue_session(auth.User("s", "someone@edvoy.com"))
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token)
    assert err.value.status_code == 401
    assert "expired" in str(err.value.detail)


def test_narrowing_the_domains_ends_outstanding_sessions(monkeypatch):
    token, _ = auth.issue_session(auth.User("s", "someone@edvoy.com"))
    monkeypatch.setattr(settings, "auth_allowed_domains", ["elsewhere.com"])
    with pytest.raises(auth.AuthError) as err:
        auth.verify(token)
    assert err.value.status_code == 403


@pytest.mark.parametrize("email,ok", [
    ("Someone@Edvoy.com", True),        # case folded on both sides
    ("  someone@edvoy.com  ", True),    # trimmed
    ("someone@notedvoy.com", False),    # not a suffix match: the domain is exact
    ("someone@edvoy.com.attacker.io", False),
    ("someone@sub.edvoy.com", False),
    ("edvoy.com", False),               # a bare domain is not an address
    ("", False),
])
def test_allow_list_matching(email, ok):
    assert auth._allowed(email) is ok


# --- the sign-in endpoint -----------------------------------------------------

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")

    @app.get("/api/whoami")
    def whoami(user: auth.User | None = Depends(auth.current_user)):
        return {"email": user.email if user else None}

    return TestClient(app)


def test_signing_in_yields_a_session_the_api_accepts(client):
    res = client.post("/api/auth/google", json={"credential": google_token()})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "someone@edvoy.com"
    assert body["expires_at"] > time.time()

    who = client.get("/api/whoami", headers={"Authorization": f"Bearer {body['token']}"})
    assert who.json() == {"email": "someone@edvoy.com"}


def test_signing_in_from_outside_the_domain_yields_no_session(client):
    res = client.post("/api/auth/google",
                      json={"credential": google_token(email="stranger@gmail.com", drop=["hd"])})
    assert res.status_code == 403
    assert "token" not in res.json()


def test_a_request_without_a_session_is_401(client):
    assert client.get("/api/whoami").status_code == 401


# --- startup ------------------------------------------------------------------

def test_preflight_is_quiet_when_configured():
    assert auth.preflight() == []


def test_preflight_refuses_auth_without_a_domain(monkeypatch):
    """Requiring auth but admitting every Google account is the worst of both:
    it looks protected."""
    monkeypatch.setattr(settings, "auth_allowed_domains", [])
    assert any("ALLOWED_DOMAINS" in p for p in auth.preflight())


def test_preflight_refuses_auth_without_a_client_id(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    assert any("GOOGLE_CLIENT_ID" in p for p in auth.preflight())


@pytest.mark.parametrize("secret", ["", "short"])
def test_preflight_refuses_a_missing_or_guessable_session_secret(monkeypatch, secret):
    monkeypatch.setattr(settings, "auth_session_secret", secret)
    assert any("AUTH_SESSION_SECRET" in p for p in auth.preflight())


def test_preflight_is_quiet_when_auth_is_off(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "auth_session_secret", "")
    assert auth.preflight() == []


def test_audit_actor_prefers_the_signed_in_identity():
    assert auth.audit_actor(auth.User("s", "a@edvoy.com")) == "a@edvoy.com"
    assert auth.audit_actor(None) is None
