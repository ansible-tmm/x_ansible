#!/usr/bin/python
"""
Ansible module to publish a post to LinkedIn via the Posts API.

Authentication: OAuth 2.0 Bearer Token
Endpoint:      POST https://api.linkedin.com/rest/posts
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: linkedin_post
short_description: Post a message to LinkedIn
version_added: "1.0.0"
description:
  - Publishes a text post to your LinkedIn personal profile via the Posts API.
  - Uses OAuth 2.0 bearer token authentication (free tier).
  - Posting is inherently non-idempotent; every successful run creates a new post.
options:
  text:
    description: The text content of the post (1-3000 characters).
    required: true
    type: str
  url:
    description: >-
      An optional URL to attach as a link preview card (article share).
      If provided, LinkedIn will generate a rich preview with title, image, and description.
    required: false
    type: str
  access_token:
    description: >-
      LinkedIn OAuth 2.0 access token.
      Falls back to LINKEDIN_ACCESS_TOKEN env var, then ~/.x_ansible/linkedin.json.
    required: false
    type: str
  person_urn:
    description: >-
      Your LinkedIn person URN (e.g. urn:li:person:abc123).
      Falls back to LINKEDIN_PERSON_URN env var, then ~/.x_ansible/linkedin.json.
    required: false
    type: str
  visibility:
    description: Post visibility.
    required: false
    type: str
    default: PUBLIC
    choices: ['PUBLIC', 'CONNECTIONS']
  api_version:
    description: LinkedIn API version string (YYYYMM format).
    required: false
    type: str
    default: "202504"
author:
  - Sean (@sean)
"""

EXAMPLES = r"""
- name: Post to LinkedIn using saved token
  linkedin_post:
    text: "Hello from Ansible!"

- name: Post with explicit credentials
  linkedin_post:
    text: "{{ post_text }}"
    access_token: "{{ vault_linkedin_access_token }}"
    person_urn: "{{ vault_linkedin_person_urn }}"
"""

RETURN = r"""
post_urn:
  description: The URN header returned for the created post.
  type: str
  returned: success
response_status:
  description: HTTP status code from LinkedIn.
  type: int
  returned: always
response_body:
  description: Response body (empty on 201 success, JSON on error).
  type: dict
  returned: always
"""

import json
import os
import traceback
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

POSTS_URL = "https://api.linkedin.com/rest/posts"
MAX_POST_LENGTH = 3000
CONFIG_FILE = Path.home() / ".x_ansible" / "linkedin.json"


def _load_config():
    """Load saved config from setup script if available."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _resolve_credential(module_param, env_var, config_key, config):
    """Resolve credential from param → env var → config file."""
    if module_param:
        return module_param, None
    value = os.environ.get(env_var)
    if value:
        return value, None
    value = config.get(config_key)
    if value:
        return value, None
    return None, (
        f"Missing: provide module parameter, set {env_var} env var, "
        f"or run 'python linkedin/files/setup_linkedin_token.py'."
    )


def run_module():
    module_args = dict(
        text=dict(type="str", required=True),
        url=dict(type="str", required=False, default=None),
        access_token=dict(type="str", required=False, default=None, no_log=True),
        person_urn=dict(type="str", required=False, default=None),
        visibility=dict(type="str", default="PUBLIC", choices=["PUBLIC", "CONNECTIONS"]),
        api_version=dict(type="str", default="202607"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if not HAS_REQUESTS:
        module.fail_json(msg="The 'requests' Python package is required.")

    text = module.params["text"].strip()
    if not text:
        module.fail_json(msg="'text' must not be empty or whitespace-only.")

    if len(text) > MAX_POST_LENGTH:
        module.fail_json(
            msg=f"Post text is {len(text)} characters; LinkedIn maximum is {MAX_POST_LENGTH}."
        )

    config = _load_config()

    access_token, err = _resolve_credential(
        module.params["access_token"], "LINKEDIN_ACCESS_TOKEN", "access_token", config
    )
    if err:
        module.fail_json(msg=err)

    person_urn, err = _resolve_credential(
        module.params["person_urn"], "LINKEDIN_PERSON_URN", "person_urn", config
    )
    if err:
        module.fail_json(msg=err)

    result = dict(changed=False, post_urn="", response_status=0, response_body={})

    if module.check_mode:
        result["changed"] = True
        module.exit_json(**result)

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": module.params["api_version"],
        }

        payload = {
            "author": person_urn,
            "commentary": text,
            "visibility": module.params["visibility"],
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "PUBLISHED",
        }

        url = module.params["url"]
        if url:
            payload["content"] = {
                "article": {
                    "source": url,
                    "title": "",
                },
            }

        resp = requests.post(POSTS_URL, headers=headers, json=payload, timeout=15)
        result["response_status"] = resp.status_code

        # LinkedIn returns 201 with empty body on success, post URN in header
        if resp.status_code == 201:
            result["changed"] = True
            result["post_urn"] = resp.headers.get("x-restli-id", "")
            module.exit_json(**result)

        # Parse error body
        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError):
            body = {"raw": resp.text}
        result["response_body"] = body

        if resp.status_code == 401:
            module.fail_json(
                msg=(
                    "Authentication failed (401). Your token may have expired. "
                    "Re-run: python linkedin/files/setup_linkedin_token.py"
                ),
                **result,
            )
        elif resp.status_code == 403:
            module.fail_json(
                msg=(
                    "Forbidden (403). Ensure 'Share on LinkedIn' product is enabled "
                    "and your token has the w_member_social scope."
                ),
                **result,
            )
        elif resp.status_code == 429:
            module.fail_json(msg="Rate limited (429). Wait and retry.", **result)
        else:
            module.fail_json(
                msg=f"LinkedIn API returned HTTP {resp.status_code}: {body}",
                **result,
            )

    except requests.exceptions.Timeout:
        module.fail_json(msg="Request timed out.", **result)
    except requests.exceptions.ConnectionError:
        module.fail_json(msg="Connection failed. Check network.", **result)
    except Exception:
        module.fail_json(msg=f"Unhandled exception: {traceback.format_exc()}", **result)


def main():
    run_module()


if __name__ == "__main__":
    main()
