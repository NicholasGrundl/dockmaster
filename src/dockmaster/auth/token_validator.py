"""Access token validation via Google's tokeninfo API."""


from collections.abc import Set

import httpx

DEFAULT_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def validate_access_token(
    token: str,
    authorized_audiences: Set[str],
    http_client: httpx.AsyncClient | None = None,
    tokeninfo_url: str = DEFAULT_TOKENINFO_URL,
) -> dict:
    """Validate a Google access token via the tokeninfo endpoint.

    Args:
        token: The access token to validate.
        authorized_audiences: Allowed audience values.
        http_client: Optional httpx client (for testing). Creates one if not provided.
        tokeninfo_url: The tokeninfo endpoint URL.

    Returns:
        The tokeninfo response dict (contains email, aud, scope, etc.).

    Raises:
        ValueError: If the token is invalid or the audience is not allowed.
    """
    should_close = False
    if http_client is None:
        http_client = httpx.AsyncClient()
        should_close = True

    try:
        response = await http_client.get(tokeninfo_url, params={"access_token": token})
    finally:
        if should_close:
            await http_client.aclose()

    if response.status_code != 200:
        raise ValueError("Invalid access token")

    claims = response.json()

    audience = claims.get("aud", "")
    if audience not in authorized_audiences:
        raise ValueError(f"Audience not allowed: {audience}")

    return claims
