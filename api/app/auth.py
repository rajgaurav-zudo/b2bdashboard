"""Google sign-in, limited to the company's Workspace domain.

The browser gets an ID token from Google Identity Services and posts it to
`/api/auth/google`. This module checks that token against Google's published
keys, decides whether that account is allowed in at all, and then hands back a
session token of its own -- which is what every other request carries.

Authentication is not authorization. Anyone with a Google account can obtain a
correctly signed ID token for this client, so "the signature is valid" proves
only that someone clicked the button. `auth_allowed_domains` decides who actually
gets a dashboard, and it is matched against two claims: the address, and `hd`,
the Workspace the account belongs to. The second one matters -- a personal
Google account can be registered under a company address, and it carries no `hd`.

Why a session token rather than the ID token itself: Google's lasts an hour and
the browser cannot renew it silently. The exchange happens once per sign-in and
the API signs its own with `auth_session_secret`.

On top of the domain, the account must be on the user list (`core.users`, see
`users.py`) and switched on. That is checked at sign-in and again on every
request, so removing someone takes effect at their next click.
"""
import time
from dataclasses import dataclass

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel

from . import users
from .config import settings

GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
# Google documents both spellings and issues either.
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
SESSION_ISSUER = "b2b-dashboards"
# Long enough that a guessed secret is not the weak point of an HS256 token.
SESSION_SECRET_MIN = 32


@dataclass(frozen=True)
class User:
    sub: str
    email: str
    name: str = ""
    role: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")

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
    so Google rotating its keys does not need a redeploy."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(GOOGLE_JWKS, cache_keys=True, lifespan=settings.auth_jwks_ttl)
    return _jwk_client


def _domains() -> set[str]:
    return {d.strip().lower().lstrip("@") for d in settings.auth_allowed_domains if d.strip()}


def _allowed(email: str) -> bool:
    """Who may use the dashboard, independent of who may hold a valid token."""
    email = (email or "").strip().lower()
    # rpartition returns the whole string as the tail when there is no separator,
    # so a claim of "edvoy.com" would otherwise match the domain "edvoy.com".
    local, at, domain = email.rpartition("@")
    if not at or not local or not domain:
        return False
    return domain in _domains()


def verify_google(credential: str) -> User:
    """Check a Google ID token and the account behind it."""
    try:
        key = _jwks().get_signing_key_from_jwt(credential).key
    except Exception as exc:  # noqa: BLE001 -- unknown kid, JWKS unreachable, malformed token
        raise AuthError(f"could not check the Google sign-in: {exc}") from exc

    try:
        claims = jwt.decode(
            credential,
            key,
            algorithms=["RS256"],
            # the token must have been issued to this app, not merely by Google
            audience=settings.google_client_id,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("the Google sign-in has expired, try again") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid Google sign-in: {exc}") from exc
    if claims["iss"] not in GOOGLE_ISSUERS:
        raise AuthError("invalid Google sign-in: not issued by Google")

    email = str(claims.get("email") or "")
    hosted = str(claims.get("hd") or "").lower()
    if claims.get("email_verified") is not True or hosted not in _domains() or not _allowed(email):
        # 403, not 401: the sign-in is genuine, this account is simply not one of
        # ours. Signing in again with the same account would not help.
        raise AuthError(
            f"only {_domain_list()} accounts can use the dashboard", 403)

    return User(sub=str(claims["sub"]), email=email.strip().lower(), name=str(claims.get("name") or ""))


def admit(user: User) -> User:
    """Is this account on the user list, and switched on? The domain check has
    already passed: this is the difference between working here and having been
    given the dashboard."""
    row = users.get(user.email)
    owner = settings.auth_owner_email.strip().lower()
    if row is None:
        raise AuthError(f"{user.email} has not been given access yet. Ask {owner or 'an admin'} to add you.", 403)
    if not row["active"]:
        raise AuthError(f"access for {user.email} has been switched off. Ask {owner or 'an admin'}.", 403)
    return User(sub=user.sub, email=user.email, name=user.name or row["name"], role=row["role"])


def _domain_list() -> str:
    return " or ".join(f"@{d}" for d in sorted(_domains()))


def issue_session(user: User) -> tuple[str, int]:
    """The token the browser holds from here on, and when it stops working."""
    expires = int(time.time()) + settings.auth_session_hours * 3600
    token = jwt.encode(
        # no role in here: it is read from the user list on every request, so a
        # change applies at once rather than at the next sign-in
        {"iss": SESSION_ISSUER, "sub": user.sub, "email": user.email, "name": user.name, "exp": expires},
        settings.auth_session_secret,
        algorithm="HS256",
    )
    return token, expires


def verify(token: str) -> User:
    try:
        claims = jwt.decode(
            token,
            settings.auth_session_secret,
            algorithms=["HS256"],
            issuer=SESSION_ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("session has expired, sign in again") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid session: {exc}") from exc

    email = str(claims.get("email") or "")
    if not _allowed(email):
        # Checked again on every request, so narrowing the list takes effect at
        # once rather than when the outstanding sessions run out.
        raise AuthError("this account is not permitted to use the dashboard", 403)

    row = users.get(email)
    if row is None or not row["active"]:
        # 401, not 403: the session is what has stopped being good, so the
        # browser drops it and the sign-in page explains why on the next try
        raise AuthError("your access has been removed, sign in again")

    return User(sub=str(claims["sub"]), email=email, name=str(claims.get("name") or ""), role=row["role"])


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


def require_admin(user: User | None = Depends(current_user)) -> User:
    """Owners and admins. With sign-in switched off there is nobody to be one."""
    if user is None:
        raise HTTPException(404, "user management needs sign-in (AUTH_REQUIRED=false)")
    if not user.is_admin:
        raise HTTPException(403, "only an admin can manage users")
    return user


def audit_actor(user: User | None) -> str | None:
    """What to record against an upload. None when auth is off, so the changelog
    says 'unknown' rather than inventing an actor."""
    return user.label if user else None


def preflight() -> list[str]:
    """Refuse to start misconfigured. Called once at startup.

    An API that requires auth but cannot verify a sign-in, or that lets anyone
    with a Google account in, is worse than one that is honestly open: it looks
    protected.
    """
    problems: list[str] = []
    if not settings.auth_required:
        return problems
    if not settings.google_client_id:
        problems.append("AUTH_REQUIRED is on but GOOGLE_CLIENT_ID is not set")
    if len(settings.auth_session_secret) < SESSION_SECRET_MIN:
        problems.append(
            f"AUTH_REQUIRED is on but AUTH_SESSION_SECRET is missing or shorter than "
            f"{SESSION_SECRET_MIN} characters (generate one with `openssl rand -hex 32`)"
        )
    if not _domains():
        problems.append(
            "AUTH_REQUIRED is on but AUTH_ALLOWED_DOMAINS is empty; "
            "every Google account would be admitted"
        )
    if not _allowed(settings.auth_owner_email):
        # with no owner who can sign in, nobody can add anyone
        problems.append(
            f"AUTH_REQUIRED is on but AUTH_OWNER_EMAIL ({settings.auth_owner_email or 'unset'}) "
            f"is not an address in AUTH_ALLOWED_DOMAINS"
        )
    return problems


def warmup() -> str:
    """Fetch the JWKS at startup so the first sign-in does not pay for it, and so
    an unreachable Google is a boot failure rather than a 500 later."""
    started = time.monotonic()
    keys = _jwks().get_jwk_set().keys
    return f"{len(keys)} signing key(s) in {1000 * (time.monotonic() - started):.0f}ms"


# --- sign-in ------------------------------------------------------------------
# Mounted at /api/auth, outside the router that requires a session: this is the
# one call a browser has to be able to make without one.
router = APIRouter()


class GoogleSignIn(BaseModel):
    credential: str


@router.post("/google")
def sign_in_with_google(body: GoogleSignIn):
    if not settings.auth_required:
        raise HTTPException(404, "sign-in is switched off (AUTH_REQUIRED=false)")
    user = admit(verify_google(body.credential))
    users.signed_in(user.email, user.name)
    token, expires = issue_session(user)
    return {"token": token, "email": user.email, "name": user.name, "role": user.role, "expires_at": expires}


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    """Who the session belongs to, and their role as of now."""
    if user is None:
        raise HTTPException(404, "sign-in is switched off (AUTH_REQUIRED=false)")
    return {"email": user.email, "name": user.name, "role": user.role}
