#!/usr/bin/env python

import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from django.core.exceptions import PermissionDenied
from requests_oauthlib import OAuth2Session

from . import oauth_settings
from .openid import jwt_token_noverify, jwt_token_verify, openid_connect_urls

logger = logging.getLogger(__name__)

USERAGENT = "OMERO.oauth"


def providers() -> List[Tuple[str, str]]:
    ps = []
    for cfg in oauth_settings.OAUTH_PROVIDERS["providers"]:
        try:
            ps.append((cfg["name"], cfg["displayname"]))
        except KeyError:
            ps.append((cfg["name"], cfg["name"]))
    return ps


class OauthException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


class OauthProvider(object):
    def __init__(self, name: str, **kwargs: Any) -> None:
        """
        Create an OAuth2Session.

        Args:
            name: The OAuth provider name.
            **kwargs: Additional keyword arguments passed to OAuth2Session.
        """
        self.name = name
        cfg: Optional[Dict[str, Any]] = None
        for item in oauth_settings.OAUTH_PROVIDERS["providers"]:
            if item["name"] == name:
                cfg = item
                break
        if not cfg:
            raise ValueError("No configuration found for: {}".format(name))
        self.cfg = cfg
        self._get_urls()
        self.oauth = OAuth2Session(
            self.get("client.id"),
            scope=self.get("client.scopes"),
            redirect_uri=self.get("url.callback"),
            **kwargs,
        )

    def get(self, keypath: str, default: Any = None, raise_on_missing: bool = False) -> Any:
        keys = keypath.split(".")
        v = self.cfg
        for key in keys:
            try:
                v = v[key]
            except KeyError:
                if raise_on_missing:
                    raise KeyError("Missing configuration property {}".format(keypath))
                return default
        return v

    def set(self, keypath: str, value: Any) -> None:
        keys = keypath.split(".")
        v = self.cfg
        for key in keys[:-1]:
            try:
                v = v[key]
            except KeyError:
                v[key] = {}
        v[keys[-1]] = value

    def _get_urls(self) -> None:
        authorization_url = self.get("url.authorisation")
        token_url = self.get("url.token")
        userinfo_url = self.get("url.userinfo")
        if not all((authorization_url, token_url, userinfo_url)):
            authorization_oid, token_oid, userinfo_oid = openid_connect_urls(
                self.get("openid.issuer", raise_on_missing=True)
            )
            if not authorization_url:
                self.set("url.authorisation", authorization_oid)
            if not token_url:
                self.set("url.token", token_oid)
            if not userinfo_url:
                self.set("url.userinfo", userinfo_oid)

    def authorization(self) -> Tuple[str, str]:
        authorization_url, state = self.oauth.authorization_url(
            self.get("url.authorisation"), **self.get("authorization.params", {})
        )
        return authorization_url, state

    def token(self, code: str) -> Dict[str, Any]:
        token = self.oauth.fetch_token(
            self.get("url.token"), client_secret=self.get("client.secret"), code=code
        )
        return cast(Dict[str, Any], token)

    # user information

    def _expand_template(self, name: str, args: Dict[str, Any]) -> str:
        template = self.get("user.{}".format(name))
        # Replace None with ''
        args = dict((k, v if v is not None else "") for k, v in list(args.items()))
        return cast(str, template.format(**args))

    def _expand_all(self, args: Dict[str, Any]) -> Tuple[str, Optional[str], str, str]:
        omename = self._expand_template("name", args)
        email = self._expand_template("email", args)
        firstname = self._expand_template("firstname", args)
        lastname = self._expand_template("lastname", args)
        return omename, email, firstname, lastname

    def get_userinfo(self, token: Dict[str, Any]) -> Tuple[str, Optional[str], str, str]:
        userinfo_type = self.get("userinfo.type", "default")
        f = getattr(self, "userinfo_{}".format(userinfo_type))
        userinfo_url = self.get("url.userinfo")
        userinfo = f(token, userinfo_url)
        return cast(Tuple[str, Optional[str], str, str], userinfo)

    def userinfo_default(
        self, token: Dict[str, Any], userinfo_url: str
    ) -> Tuple[str, Optional[str], str, str]:
        userinfo = self.oauth.get(userinfo_url).json()
        logger.debug("Got raw userinfo %s", userinfo)
        return self._expand_all(userinfo)

    def userinfo_keycloak(
        self, token: Any, userinfo_url: str
    ) -> Tuple[str, Optional[str], str, str]:
        response = self.oauth.get(
            userinfo_url, headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code != 200:
            raise OauthException(
                f"Failed to fetch userinfo: {response.status_code} {response.text}"
            )
        userinfo = response.json()
        logger.debug("Got Keycloak userinfo %s", userinfo)
        omename = self._expand_template("name", userinfo)
        email = self._expand_template("email", userinfo)
        firstname = self._expand_template("firstname", userinfo)
        lastname = self._expand_template("lastname", userinfo)
        if not omename or not email:
            raise OauthException(
                "Required fields 'omename' or 'email' are missing from Keycloak userinfo."
            )
        return omename, email, firstname, lastname

    def userinfo_synapse(
        self, token: Dict[str, Any], userinfo_url: str
    ) -> Tuple[str, Optional[str], str, str]:
        decoded = jwt_token_noverify(token["id_token"])

        omename = decoded["user_name"]
        email = decoded.get("email")
        firstname = decoded.get("given_name", "")
        lastname = decoded.get("family_name", "")
        team = decoded.get("team")
        if not team or len(team) == 0:
            raise OauthException(
                "Required team not found, request membership from your Synapse team manager."
            )

        return omename, email, firstname, lastname

    def userinfo_github(
        self, token: Dict[str, Any], userinfo_url: str
    ) -> Tuple[str, Optional[str], str, str]:
        # Note userinfo_default() will work if the user's email is public
        # otherwise we need another API call:
        # https://stackoverflow.com/a/35387123/8062212
        userinfo = self.oauth.get(userinfo_url).json()
        logger.debug("Got GitHub userinfo %s", userinfo)
        emailinfo = self.oauth.get(userinfo_url + "/emails").json()
        logger.debug("Got GitHub emails %s", emailinfo)

        omename = self._expand_template("name", userinfo)
        ghname = userinfo["name"].split()
        firstname = ghname[0]
        lastname = ghname[-1]
        try:
            email = [e for e in emailinfo if e["primary"]][0]["email"]
        except IndexError:
            email = self._expand_template("email", userinfo)
        return omename, email, firstname, lastname

    def userinfo_orcid(
        self, token: Dict[str, Any], userinfo_url: str
    ) -> Tuple[str, str, str, str]:
        from xml.etree import ElementTree

        userinfo = self.oauth.get(userinfo_url.format(**token))
        logger.debug("Got ORCID userinfo %s", userinfo)

        namespaces = {
            "person": "http://www.orcid.org/ns/person",
            "personal-details": "http://www.orcid.org/ns/personal-details",
        }
        root = ElementTree.fromstring(userinfo.text)
        persons = root.findall(".//person:person/person:name", namespaces)
        assert len(persons) == 1
        person = persons[0]

        omename = self._expand_template("name", token)
        # Not available in public API
        email = ""
        firstname_el = person.find("personal-details:given-names", namespaces)
        lastname_el = person.find("personal-details:family-name", namespaces)
        firstname = (firstname_el.text if firstname_el is not None else "") or ""
        lastname = (lastname_el.text if lastname_el is not None else "") or ""

        return omename, email, firstname, lastname

    def userinfo_openid(
        self, token: Dict[str, Any], userinfo_url: str
    ) -> Tuple[str, Optional[str], str, str]:
        if self.get("openid.verify"):
            decoded = jwt_token_verify(
                token["id_token"], self.get("client.id"), self.get("openid.issuer")
            )
        else:
            decoded = jwt_token_noverify(token["id_token"])

        # Attempt to fill fields from token, if not possible then merge in
        # fields from userinfo
        try:
            omename, email, firstname, lastname = self._expand_all(decoded)
        except KeyError:
            userinfo = self.oauth.get(userinfo_url).json()
            logger.debug("Got openid userinfo %s", userinfo)
            userinfo.update(decoded)
            omename, email, firstname, lastname = self._expand_all(userinfo)
        return omename, email, firstname, lastname
