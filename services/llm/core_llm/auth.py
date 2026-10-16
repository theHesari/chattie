"""Bearer-token auth: the web app (Better Auth, JWT plugin) signs short-lived tokens;
this service verifies them against the web app's public keys (JWKS)."""

import asyncio
import logging
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Settings

logger = logging.getLogger(__name__)

ALGORITHMS = ["EdDSA"]  # Better Auth's default key pair (Ed25519)

_bearer = HTTPBearer(auto_error=False)


def build_jwks_client(settings: Settings) -> jwt.PyJWKClient:
    # Keys are cached; an unknown `kid` (key rotation) triggers a refetch.
    # Generous timeout: in dev, Next compiles the JWKS route on its first request.
    return jwt.PyJWKClient(settings.AUTH_JWKS_URL, cache_keys=True, timeout=15)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Verified user id (`sub`) of the caller, or 401."""
    if credentials is None:
        raise _unauthorized("missing bearer token")

    settings: Settings = request.app.state.settings
    jwks: jwt.PyJWKClient = request.app.state.jwks
    token = credentials.credentials
    try:
        # Fetching keys does blocking HTTP on a cache miss; keep it off the event loop.
        signing_key = await asyncio.to_thread(jwks.get_signing_key_from_jwt, token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=settings.AUTH_AUDIENCE,
            issuer=settings.AUTH_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWKClientConnectionError as exc:
        logger.error("cannot reach JWKS at %s: %s", settings.AUTH_JWKS_URL, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth service unavailable") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("invalid or expired token") from exc

    return claims["sub"]


CurrentUserId = Annotated[str, Depends(current_user_id)]
