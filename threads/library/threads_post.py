#!/usr/bin/python
"""
Ansible module to publish a post to Threads (Meta) via the Threads API.

Authentication: OAuth 2.0 long-lived access token
Endpoint:      https://graph.threads.net/v1.0/{user_id}/threads (create container)
               https://graph.threads.net/v1.0/{user_id}/threads_publish (publish)

The Threads API requires a two-step publish process:
1. Create a media container with the post content
2. Publish the container
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: threads_post
short_description: Post a message to Threads (Meta)
version_added: "1.0.0"
description:
  - Publishes a text post to Threads using the Threads API.
  - Uses the two-step container publish flow (create + publish).
  - Supports text posts and text + link posts.
  - Posting is inherently non-idempotent; every successful run creates a new post.
options:
  text:
    description: The text content of the post (max 500 chars).
    required: true
    type: str
  url:
    description: >-
      An optional URL to attach as a link attachment.
      If provided, the post becomes a link-type post with a preview card.
    required: false
    type: str
  access_token:
    description: >-
      Threads API long-lived access token.
      Falls back to THREADS_ACCESS_TOKEN env var, then threads/vars/token.json.
    required: false
    type: str
  user_id:
    description: >-
      Threads user ID.
      Falls back to THREADS_USER_ID env var, then threads/vars/token.json.
    required: false
    type: str
author:
  - Sean (@IPvSean)
"""

EXAMPLES = r"""
- name: Post text to Threads
  threads_post:
    text: "Hello from Ansible automation!"

- name: Post with a link
  threads_post:
    text: "Check out this new Ansible collection for network automation"
    url: "https://github.com/example/collection"

- name: Post with explicit credentials
  threads_post:
    text: "{{ post_text }}"
    access_token: "{{ threads_token }}"
    user_id: "{{ threads_user_id }}"
"""

RETURN = r"""
container_id:
  description: The media container ID created in step 1.
  type: str
  returned: success
post_id:
  description: The ID of the published post.
  type: str
  returned: success
permalink:
  description: The permalink URL of the published post (if available).
  type: str
  returned: success
"""

import json
import os
import time
import traceback
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

API_BASE = "https://graph.threads.net/v1.0"
MAX_TEXT_LENGTH = 500
TOKEN_FILE = Path(__file__).resolve().parent.parent / "vars" / "token.json"


def load_token_file():
    """Load saved token data from threads/vars/token.json."""
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return data.get("access_token"), data.get("user_id")
        except (json.JSONDecodeError, KeyError):
            pass
    return None, None


def resolve_credentials(module_token, module_user_id):
    """Resolve access token and user ID from params, env, or file."""
    token = module_token or os.environ.get("THREADS_ACCESS_TOKEN")
    user_id = module_user_id or os.environ.get("THREADS_USER_ID")

    if not token or not user_id:
        file_token, file_user_id = load_token_file()
        token = token or file_token
        user_id = user_id or file_user_id

    return token, user_id


def create_container(user_id, access_token, text, url=None):
    """Step 1: Create a media container."""
    endpoint = f"{API_BASE}/{user_id}/threads"
    params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": access_token,
    }

    if url:
        params["link_attachment"] = url

    resp = requests.post(endpoint, params=params, timeout=15)

    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        body = {"raw": resp.text}

    if resp.status_code == 200 and "id" in body:
        return body["id"], None
    else:
        error = body.get("error", {})
        msg = error.get("message", resp.text) if isinstance(error, dict) else str(body)
        return None, f"Container creation failed (HTTP {resp.status_code}): {msg}"


def publish_container(user_id, access_token, container_id):
    """Step 2: Publish the media container."""
    endpoint = f"{API_BASE}/{user_id}/threads_publish"
    params = {
        "creation_id": container_id,
        "access_token": access_token,
    }

    resp = requests.post(endpoint, params=params, timeout=15)

    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        body = {"raw": resp.text}

    if resp.status_code == 200 and "id" in body:
        return body["id"], None
    else:
        error = body.get("error", {})
        msg = error.get("message", resp.text) if isinstance(error, dict) else str(body)
        return None, f"Publish failed (HTTP {resp.status_code}): {msg}"


def get_permalink(post_id, access_token):
    """Fetch the permalink for a published post."""
    endpoint = f"{API_BASE}/{post_id}"
    params = {
        "fields": "permalink",
        "access_token": access_token,
    }

    try:
        resp = requests.get(endpoint, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("permalink", "")
    except Exception:
        pass
    return ""


def run_module():
    module_args = dict(
        text=dict(type="str", required=True),
        url=dict(type="str", required=False, default=None),
        access_token=dict(type="str", required=False, default=None, no_log=True),
        user_id=dict(type="str", required=False, default=None),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    if not HAS_REQUESTS:
        module.fail_json(msg="The 'requests' Python package is required.")

    text = module.params["text"].strip()
    if not text:
        module.fail_json(msg="'text' must not be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        module.fail_json(
            msg=f"Text is {len(text)} characters; Threads maximum is {MAX_TEXT_LENGTH}."
        )

    url = module.params["url"]
    access_token, user_id = resolve_credentials(
        module.params["access_token"],
        module.params["user_id"],
    )

    if not access_token:
        module.fail_json(
            msg="No access token found. Provide 'access_token' parameter, "
                "set THREADS_ACCESS_TOKEN env var, or run: "
                "python threads/files/setup_threads_token.py"
        )
    if not user_id:
        module.fail_json(
            msg="No user ID found. Provide 'user_id' parameter, "
                "set THREADS_USER_ID env var, or run: "
                "python threads/files/setup_threads_token.py"
        )

    result = dict(changed=False, container_id="", post_id="", permalink="")

    if module.check_mode:
        result["changed"] = True
        module.exit_json(**result)

    try:
        # Step 1: Create container
        container_id, err = create_container(user_id, access_token, text, url=url)
        if err:
            module.fail_json(msg=err, **result)
        result["container_id"] = container_id

        # Brief pause for container processing
        time.sleep(2)

        # Step 2: Publish
        post_id, err = publish_container(user_id, access_token, container_id)
        if err:
            module.fail_json(msg=err, **result)

        result["changed"] = True
        result["post_id"] = post_id

        # Try to get permalink
        time.sleep(1)
        result["permalink"] = get_permalink(post_id, access_token)

        module.exit_json(**result)

    except requests.exceptions.Timeout:
        module.fail_json(msg="Request timed out. Check network connectivity.", **result)
    except requests.exceptions.ConnectionError:
        module.fail_json(msg="Connection failed. Check network/DNS.", **result)
    except Exception:
        module.fail_json(msg=f"Unhandled exception: {traceback.format_exc()}", **result)


def main():
    run_module()


if __name__ == "__main__":
    main()
