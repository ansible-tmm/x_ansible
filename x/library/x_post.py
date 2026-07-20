#!/usr/bin/python

"""
Ansible module to publish a post (tweet) to X (Twitter) via the v2 API.

Authentication: OAuth 1.0a User Context
Endpoint:      POST https://api.x.com/2/tweets
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: x_post
short_description: Post a message to X (Twitter)
version_added: "1.0.0"
description:
  - Publishes a text post to X using the v2 API with OAuth 1.0a user context.
  - Posting is inherently non-idempotent; every successful run creates a new post.
options:
  text:
    description: The text content of the post (1-280 characters).
    required: true
    type: str
  api_key:
    description: X API key (consumer key). Falls back to X_API_KEY env var.
    required: false
    type: str
  api_secret:
    description: X API secret (consumer secret). Falls back to X_API_SECRET env var.
    required: false
    type: str
  access_token:
    description: OAuth 1.0a access token. Falls back to X_ACCESS_TOKEN env var.
    required: false
    type: str
  access_token_secret:
    description: OAuth 1.0a access token secret. Falls back to X_ACCESS_TOKEN_SECRET env var.
    required: false
    type: str
author:
  - Sean (@sean)
"""

EXAMPLES = r"""
- name: Post to X using environment variables for credentials
  x_post:
    text: "Hello from Ansible!"

- name: Post to X with explicit credentials (use Vault in practice)
  x_post:
    text: "{{ post_text }}"
    api_key: "{{ vault_x_api_key }}"
    api_secret: "{{ vault_x_api_secret }}"
    access_token: "{{ vault_x_access_token }}"
    access_token_secret: "{{ vault_x_access_token_secret }}"
"""

RETURN = r"""
post_id:
  description: The ID of the created post.
  type: str
  returned: success
post_text:
  description: The text of the created post as returned by X.
  type: str
  returned: success
response:
  description: The full JSON response body from the X API.
  type: dict
  returned: always
"""

import json
import os
import traceback

from ansible.module_utils.basic import AnsibleModule

try:
    from requests_oauthlib import OAuth1Session
    HAS_REQUESTS_OAUTHLIB = True
except ImportError:
    HAS_REQUESTS_OAUTHLIB = False

X_API_URL = "https://api.x.com/2/tweets"
MAX_POST_LENGTH = 280


def _resolve_credential(module_param, env_var_name):
    """Return the module parameter if set, otherwise the environment variable."""
    value = module_param or os.environ.get(env_var_name)
    if not value:
        return None, (
            f"Missing credential: provide '{env_var_name.lower()}' parameter "
            f"or set the {env_var_name} environment variable."
        )
    return value, None


def run_module():
    module_args = dict(
        text=dict(type="str", required=True),
        api_key=dict(type="str", required=False, default=None, no_log=True),
        api_secret=dict(type="str", required=False, default=None, no_log=True),
        access_token=dict(type="str", required=False, default=None, no_log=True),
        access_token_secret=dict(type="str", required=False, default=None, no_log=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if not HAS_REQUESTS_OAUTHLIB:
        module.fail_json(
            msg=(
                "The 'requests-oauthlib' Python package is required. "
                "Install it with: pip install requests-oauthlib"
            ),
        )

    text = module.params["text"].strip()
    if not text:
        module.fail_json(msg="'text' must not be empty or whitespace-only.")

    if len(text) > MAX_POST_LENGTH:
        module.fail_json(
            msg=f"Post text is {len(text)} characters; maximum is {MAX_POST_LENGTH}."
        )

    credentials = {}
    cred_map = {
        "api_key": "X_API_KEY",
        "api_secret": "X_API_SECRET",
        "access_token": "X_ACCESS_TOKEN",
        "access_token_secret": "X_ACCESS_TOKEN_SECRET",
    }

    for param_name, env_name in cred_map.items():
        value, error = _resolve_credential(module.params[param_name], env_name)
        if error:
            module.fail_json(msg=error)
        credentials[param_name] = value

    result = dict(changed=False, post_id="", post_text="", response={})

    if module.check_mode:
        result["changed"] = True
        result["post_text"] = text
        module.exit_json(**result)

    try:
        session = OAuth1Session(
            client_key=credentials["api_key"],
            client_secret=credentials["api_secret"],
            resource_owner_key=credentials["access_token"],
            resource_owner_secret=credentials["access_token_secret"],
        )

        payload = {"text": text}
        response = session.post(X_API_URL, json=payload)

        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError):
            body = {"raw": response.text}

        result["response"] = body

        if response.status_code == 201:
            result["changed"] = True
            data = body.get("data", {})
            result["post_id"] = data.get("id", "")
            result["post_text"] = data.get("text", "")
            module.exit_json(**result)

        elif response.status_code == 401:
            module.fail_json(
                msg=(
                    "Authentication failed (HTTP 401). Verify your API key, "
                    "API secret, access token, and access token secret."
                ),
                **result,
            )

        elif response.status_code == 403:
            detail = body.get("detail", body.get("title", "Forbidden"))
            module.fail_json(
                msg=(
                    f"Forbidden (HTTP 403): {detail}. "
                    "Ensure your app has write permissions and your access token "
                    "was generated with read+write scope."
                ),
                **result,
            )

        elif response.status_code == 429:
            module.fail_json(
                msg=(
                    "Rate limit exceeded (HTTP 429). "
                    "Wait before retrying. Check x-rate-limit-reset header."
                ),
                **result,
            )

        else:
            module.fail_json(
                msg=f"X API returned HTTP {response.status_code}: {body}",
                **result,
            )

    except Exception:
        module.fail_json(
            msg=f"Unhandled exception: {traceback.format_exc()}",
            **result,
        )


def main():
    run_module()


if __name__ == "__main__":
    main()
