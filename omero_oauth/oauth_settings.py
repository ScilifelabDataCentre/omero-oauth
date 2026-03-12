import json
import sys
from pkgutil import get_data

import yaml
from jsonschema import Draft7Validator
from omeroweb.settings import process_custom_settings, report_settings


def str_not_empty(o):
    s = str(o)
    if not o or not s:
        raise ValueError("Invalid empty value")
    return s


def str_or_none(o):
    if o is not None:
        o = str(o)
    return o


# https://github.com/jupyterhub/zero-to-jupyterhub-k8s/blob/0.8.0/images/hub/z2jh.py#L33-L47
def _merge_dictionaries(a, b):
    merged = a.copy()
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merged[key] = _merge_dictionaries(a[key], b[key])
            else:
                merged[key] = b[key]
        else:
            merged[key] = b[key]
    return merged


def oauth_provider_config(o):
    """
    Args:
        o: Either a JSON object containing the full OAuth provider
            configuration, or a JSON or YAML file containing a dictionary that
            will be merged.
    """
    try:
        cfg = json.loads(o)
    except ValueError:
        cfgfile = o
        with open(cfgfile) as f:
            if cfgfile.endswith(".yml") or cfgfile.endswith(".yaml"):
                cfg = yaml.load(f, Loader=yaml.FullLoader)
            else:
                cfg = json.load(f, Loader=yaml.FullLoader)
    schemastr = get_data("omero_oauth", "schema/provider-schema.yaml")
    schema = yaml.load(schemastr, Loader=yaml.FullLoader)
    v = Draft7Validator(schema)
    if not v.is_valid(cfg):
        errs = "\n\n** ".join(
            ["Invalid provider configuration"]
            + ["\n\n".join(str(e) for e in v.iter_errors(cfg))]
        )
        raise ValueError(errs)
    return cfg


# load settings
OAUTH_SETTINGS_MAPPING = {
    "omero.web.oauth.providers": ["OAUTH_PROVIDERS", "{}", oauth_provider_config, None],
    "omero.web.oauth.display.name": ["OAUTH_DISPLAY_NAME", "OAuth Client", str, None],
    "omero.web.oauth.host": ["OAUTH_HOST", "", str_not_empty, None],
    "omero.web.oauth.port": ["OAUTH_PORT", 4064, int, None],
    "omero.web.oauth.admin.user": ["OAUTH_ADMIN_USERNAME", "", str_not_empty, None],
    "omero.web.oauth.admin.password": ["OAUTH_ADMIN_PASSWORD", "", str_not_empty, None],
    "omero.web.oauth.user.timeout": ["OAUTH_USER_TIMEOUT", 86400, int, None],
    "omero.web.oauth.group.name": ["OAUTH_GROUP_NAME", "", str_not_empty, None],
    "omero.web.oauth.group.templatetime": [
        "OAUTH_GROUP_NAME_TEMPLATETIME",
        False,
        bool,
        None,
    ],
    "omero.web.oauth.group.perms": ["OAUTH_GROUP_PERMS", "rw----", str_not_empty, None],
    "omero.web.oauth.sessiontoken.enable": [
        "OAUTH_SESSIONTOKEN_ENABLE",
        False,
        bool,
        None,
    ],
}


process_custom_settings(sys.modules[__name__], "OAUTH_SETTINGS_MAPPING")
report_settings(sys.modules[__name__])
