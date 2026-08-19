"""Supabase JWT verification.

The browser signs in with Supabase Auth and sends the resulting token here. This
module checks the signature against the project's published JWKS and then decides
whether that user is allowed in at all -- two separate questions, and only the
first one is Supabase's.

Authentication is not authorization. A Supabase project accepts public sign-ups
by default, so "the signature is valid" only proves someone reached the sign-up
form. `auth_allowed_emails` / `auth_allowed_domains` decide who actually gets a
dashboard, and one of them must be set.

Tokens are ES256 by default on current projects: the API verifies with a public
key and never holds anything that could mint a token.
"""
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import settings


@dataclass(frozen=True)
class User:
    sub: str
    email: str
    role: str

    @property
    def label(self) -> str:
        return self.email or self.sub


class AuthError(HTTPException):
    def __init__(self, detail: str, status: int = 401):
        # 401 must say how to authenticate, or a browser cannot act on it
        super().__init__(status, detail, headers={"WWW-Authenticate": "Bearer"})


_jwk_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    """Cached JWKS client. Keys are fetched once and refreshed on an unknown kid,
    so key rotation does not need a redeploy."""
    global _jwk_client
    if _jwk_client is None:
        if not settings.supabase_url:
            raise AuthError("auth is required but SUPABASE_URL is not configured", 500)
        _jwk_client = PyJWKClient(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=settings.auth_jwks_ttl,
        )
    return _jwk_client


def _allowed(email: str) -> bool:
    """Who may use the dashboard, independent of who may hold a valid token."""
    email = (email or "").strip().lower()
    if not email:
        return False
    if email in {e.strip().lower() for e in settings.auth_allowed_emails if e.strip()}:
        return True
    # rpartition returns the whole string as the tail when there is no separator,
    # so a claim of "edvoy.com" would otherwise match the domain "edvoy.com".
    local, at, domain = email.rpartition("@")
    if not at or not local or not domain:
        return False
    return domain in {
        d.strip().lower().lstrip("@") for d in settings.auth_allowed_domains if d.strip()
    }


def verify(token: str) -> User:
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001 -- unknown kid, JWKS unreachable, malformed token
        raise AuthError(f"could not check the token signature: {exc}") from exc

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=settings.auth_algorithms,
            audience=settings.auth_audience,
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token has expired, sign in again") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    email = str(claims.get("email") or "")
    if not _allowed(email):
        # 403, not 401: the token is fine, this person is simply not on the list.
        # Retrying with a new token would not help.
        raise AuthError("this account is not permitted to use the dashboard", 403)

    return User(sub=str(claims["sub"]), email=email, role=str(claims.get("role") or "authenticated"))


_bearer = HTTPBearer(auto_error=False)


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    """The signed-in user, or None when auth is switched off for local work."""
    if not settings.auth_required:
        return None
    if credentials is None or not credentials.credentials:
        raise AuthError("sign in to use this dashboard")
    user = verify(credentials.credentials)
    request.state.user = user
    return user


def audit_actor(user: User | None) -> str | None:
    """What to record against an upload. None when auth is off, so the changelog
    says 'unknown' rather than inventing an actor."""
    return user.label if user else None


def preflight() -> list[str]:
    """Refuse to start misconfigured. Called once at startup.

    An API that requires auth but cannot verify a signature, or that lets anyone
    with a token in, is worse than one that is honestly open: it looks protected.
    """
    problems: list[str] = []
    if not settings.auth_required:
        return problems
    if not settings.supabase_url:
        problems.append("AUTH_REQUIRED is on but SUPABASE_URL is not set")
    if not settings.auth_allowed_emails and not settings.auth_allowed_domains:
        problems.append(
            "AUTH_REQUIRED is on but neither AUTH_ALLOWED_EMAILS nor AUTH_ALLOWED_DOMAINS is set; "
            "every account that can sign up to the Supabase project would be admitted"
        )
    return problems


def warmup() -> str:
    """Fetch the JWKS at startup so the first request does not pay for it, and so
    an unreachable auth server is a boot failure rather than a 500 later."""
    started = time.monotonic()
    keys = _jwks().get_jwk_set().keys
    return f"{len(keys)} signing key(s) in {1000 * (time.monotonic() - started):.0f}ms"
