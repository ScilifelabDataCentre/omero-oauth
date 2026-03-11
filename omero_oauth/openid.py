import codecs
from datetime import datetime
from email.utils import parsedate
from time import mktime
from typing import Dict, Tuple

import jwt
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from jwt.utils import base64url_decode

# Cache of openid discovery responses
_DISCOVERY_CACHE = {}
# Default cache expiry time (seconds) if not in HTTP header
_DISCOVERY_CACHE_DEFAULT_EXPIRY = 1800


def _cache_get(url):
    now = mktime(datetime.now().timetuple())
    try:
        obj, expiry = _DISCOVERY_CACHE[url]
        if now < expiry:
            return obj
    except KeyError:
        pass

    r = requests.get(url)
    r.raise_for_status()
    obj = r.json()
    httpexpiry = r.headers.get("expires")
    if httpexpiry:
        expiry = mktime(parsedate(httpexpiry))
    else:
        expiry = now + _DISCOVERY_CACHE_DEFAULT_EXPIRY
    _DISCOVERY_CACHE[url] = (obj, expiry)
    return obj


class AuthException(Exception):
    def __init__(self, *args, **kwargs):
        super(AuthException, self).__init__(*args, **kwargs)


def _keycloak_urls_from_issuer(issuer: str) -> Tuple[str, str, str]:
    """Build authorization, token, userinfo URLs from a Keycloak realm issuer."""
    base = issuer.rstrip("/")
    prefix = "{}/protocol/openid-connect".format(base)
    return (
        "{}/auth".format(prefix),
        "{}/token".format(prefix),
        "{}/userinfo".format(prefix),
    )


def openid_connect_discover(issuer: str) -> Dict:
    """
    Fetch openid connect server metadata for auto-configuration.

    Args:
        issuer: The issuer, e.g. 'https://accounts.google.com'.

    Returns:
        The openid connect server information.

    Raises:
        AuthException: If issuer is missing or discovery request fails.
    """
    if not issuer:
        raise AuthException("No issuer provided")
    discovery_url = "{}/.well-known/openid-configuration".format(issuer.rstrip("/"))
    try:
        autoconfig = _cache_get(discovery_url)
    except requests.HTTPError as e:
        if "/realms/" in issuer and e.response is not None and e.response.status_code == 404:
            raise AuthException(
                "OpenID discovery failed (404) for {}. "
                "Set url.authorisation, url.token and url.userinfo explicitly in the "
                "provider config, or fix the issuer URL.".format(discovery_url)
            )
        raise AuthException("OpenID discovery failed: {}".format(e))
    except requests.RequestException as e:
        raise AuthException("OpenID discovery failed: {}".format(e))
    return autoconfig


def openid_connect_urls(issuer: str) -> Tuple[str, str, str]:
    """
    Get URLs for openid connect authentication using auto-configuration.
    For Keycloak-style issuers (containing /realms/), falls back to built-in
    paths if discovery returns 404.

    Args:
        issuer: The issuer, e.g. 'https://accounts.google.com'.

    Returns:
        A tuple of (authorization, token, userinfo) URLs.

    Raises:
        AuthException: If discovery fails and no Keycloak fallback applies.
    """
    try:
        autoconfig = openid_connect_discover(issuer)
        return (
            autoconfig["authorization_endpoint"],
            autoconfig["token_endpoint"],
            autoconfig["userinfo_endpoint"],
        )
    except AuthException as e:
        if "/realms/" in issuer and "404" in str(e):
            return _keycloak_urls_from_issuer(issuer)
        raise


def jwt_token_verify(id_token, client_id, issuer, autoconfig=None, jwk=None):
    """
    Verify a JWT token using public key.
    If jwk is not provided the issuer must support auto-discovery.
    This will also slow down the login process since multiple remote calls
    are required to fetch jwk.
    :param id_token: The openid id_token returned by the authorisation call
    :param client_id: The client_id, required for JWT verification
    :param issuer: The issuer, required for JWT verification and for
                   auto-configuration if necessary
    :param autoconfig: Dictionary of auto-configuration properties, if empty
                       will be fetched if required
    :param jwk: The JSON web key, if empty will be fetched using autoconfig
    :return dict: The decoded verified token
    :raises Exception: If verification failed
    """
    # https://pyjwt.readthedocs.io/en/latest/usage.html
    # https://openid.net/specs/openid-connect-core-1_0.html#IDToken

    if not jwk:
        header = jwt.get_unverified_header(id_token)
        if not autoconfig:
            autoconfig = openid_connect_discover(issuer)
        jwks = _cache_get(autoconfig["jwks_uri"])
        for jwk in jwks["keys"]:
            if jwk["kid"] == header["kid"]:
                break
    if not jwk:
        raise Exception("Failed to get public key for {}".format(issuer))

    e = int(codecs.encode(base64url_decode(jwk["e"]), "hex"), 16)
    n = int(codecs.encode(base64url_decode(jwk["n"]), "hex"), 16)
    public_key = RSAPublicNumbers(e, n).public_key(backend=default_backend())
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    d = jwt.decode(
        id_token, key=pem, algorithms=jwk["alg"], audience=client_id, issuer=issuer
    )
    return d


def jwt_token_noverify(id_token):
    """
    Decode a JWT token without verification.
    :param id_token: The openid id_token returned by the authorisation call
    :return dict: The decoded verified token
    """
    return jwt.decode(id_token, options={"verify_signature": False})
