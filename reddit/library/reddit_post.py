#!/usr/bin/python
"""
Ansible module to publish a post to Reddit via the Reddit Data API (OAuth2).

Authentication: Script-type OAuth app (client_id + client_secret + username + password)
Endpoint:      POST https://oauth.reddit.com/api/submit
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: reddit_post
short_description: Post a message to Reddit
version_added: "1.0.0"
description:
  - Publishes a text or link post to a Reddit subreddit or your own profile.
  - Uses OAuth2 script-type app authentication (free, non-commercial tier).
  - Posting is inherently non-idempotent; every successful run creates a new post.
options:
  title:
    description: The title of the Reddit post (required, max 300 chars).
    required: true
    type: str
  text:
    description: >-
      The body text of the post (for self/text posts).
      Mutually exclusive with 'url' - provide one or the other.
    required: false
    type: str
  url:
    description: >-
      A URL to submit as a link post.
      Mutually exclusive with 'text' - provide one or the other.
    required: false
    type: str
  subreddit:
    description: >-
      The subreddit to post to (without r/ prefix).
      Use 'u_YOURUSERNAME' to post to your own profile.
      Falls back to REDDIT_SUBREDDIT env var.
    required: false
    type: str
  flair_id:
    description: The flair ID to apply to the post (optional).
    required: false
    type: str
  client_id:
    description: >-
      Reddit OAuth app client ID.
      Falls back to REDDIT_CLIENT_ID env var.
    required: false
    type: str
  client_secret:
    description: >-
      Reddit OAuth app client secret.
      Falls back to REDDIT_CLIENT_SECRET env var.
    required: false
    type: str
  username:
    description: >-
      Reddit username.
      Falls back to REDDIT_USERNAME env var.
    required: false
    type: str
  password:
    description: >-
      Reddit password.
      Falls back to REDDIT_PASSWORD env var.
    required: false
    type: str
  user_agent:
    description: >-
      User-Agent string for Reddit API requests.
      Reddit requires a descriptive User-Agent.
    required: false
    type: str
    default: "ansible:social-poster:v1.0 (by /u/unknown)"
author:
  - Sean (@sean)
"""

EXAMPLES = r"""
- name: Post a link to a subreddit
  reddit_post:
    title: "Automating Meraki with Ansible"
    url: "https://blogs.cisco.com/developer/elevating-meraki-operations-ansible-automation"
    subreddit: "ansible"

- name: Post text to your own profile
  reddit_post:
    title: "New automation project"
    text: "Just shipped a new tool that generates social media posts with AI"
    subreddit: "u_IPvSean"

- name: Post using environment variables for credentials
  reddit_post:
    title: "{{ post_title }}"
    url: "{{ post_url }}"
    subreddit: "{{ target_subreddit }}"
"""

RETURN = r"""
post_id:
  description: The ID of the created post.
  type: str
  returned: success
post_url:
  description: The full URL of the created post.
  type: str
  returned: success
response:
  description: The full JSON response from the API.
  type: dict
  returned: always
"""

import json
import os
import traceback

from ansible.module_utils.basic import AnsibleModule

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

MAX_TITLE_LENGTH = 300


def _resolve(module_param, env_var_name):
    """Return the module parameter if set, otherwise the environment variable."""
    value = module_param or os.environ.get(env_var_name)
    if not value:
        return None, (
            f"Missing: provide '{env_var_name.lower()}' parameter "
            f"or set the {env_var_name} environment variable."
        )
    return value, None


def get_oauth_token(client_id, client_secret, username, password, user_agent):
    """Authenticate with Reddit and return (access_token, error_msg)."""
    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    headers = {"User-Agent": user_agent}
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
    }

    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth,
        headers=headers,
        data=data,
        timeout=15,
    )

    if resp.status_code != 200:
        return None, f"Auth failed (HTTP {resp.status_code}): {resp.text}"

    token_data = resp.json()
    if "access_token" not in token_data:
        error = token_data.get("error", "unknown error")
        return None, f"Auth failed: {error}"

    return token_data["access_token"], None


def submit_post(access_token, user_agent, subreddit, title, text=None, url=None, flair_id=None):
    """Submit a post to Reddit and return (response_dict, error_msg)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": user_agent,
    }

    data = {
        "api_type": "json",
        "sr": subreddit,
        "title": title,
        "resubmit": True,
    }

    if url:
        data["kind"] = "link"
        data["url"] = url
    else:
        data["kind"] = "self"
        data["text"] = text or ""

    if flair_id:
        data["flair_id"] = flair_id

    resp = requests.post(
        "https://oauth.reddit.com/api/submit",
        headers=headers,
        data=data,
        timeout=15,
    )

    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        body = {"raw": resp.text}

    if resp.status_code == 200:
        json_data = body.get("json", {})
        errors = json_data.get("errors", [])
        if errors:
            error_msgs = "; ".join([str(e) for e in errors])
            return body, f"Reddit rejected the post: {error_msgs}"
        return body, None
    elif resp.status_code == 401:
        return body, "Post failed (401). Token may have expired."
    elif resp.status_code == 403:
        return body, "Post failed (403). You may not have permission to post to this subreddit."
    elif resp.status_code == 429:
        return body, "Rate limited (429). Wait and retry."
    else:
        return body, f"Post failed (HTTP {resp.status_code}): {body}"


def run_module():
    module_args = dict(
        title=dict(type="str", required=True),
        text=dict(type="str", required=False, default=None),
        url=dict(type="str", required=False, default=None),
        subreddit=dict(type="str", required=False, default=None),
        flair_id=dict(type="str", required=False, default=None),
        client_id=dict(type="str", required=False, default=None),
        client_secret=dict(type="str", required=False, default=None, no_log=True),
        username=dict(type="str", required=False, default=None),
        password=dict(type="str", required=False, default=None, no_log=True),
        user_agent=dict(type="str", default="ansible:social-poster:v1.0 (by /u/unknown)"),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        mutually_exclusive=[("text", "url")],
    )

    if not HAS_REQUESTS:
        module.fail_json(msg="The 'requests' Python package is required.")

    title = module.params["title"].strip()
    if not title:
        module.fail_json(msg="'title' must not be empty.")
    if len(title) > MAX_TITLE_LENGTH:
        module.fail_json(
            msg=f"Title is {len(title)} characters; Reddit maximum is {MAX_TITLE_LENGTH}."
        )

    text = module.params["text"]
    url = module.params["url"]
    if not text and not url:
        module.fail_json(msg="Either 'text' or 'url' must be provided.")

    client_id, err = _resolve(module.params["client_id"], "REDDIT_CLIENT_ID")
    if err:
        module.fail_json(msg=err)

    client_secret, err = _resolve(module.params["client_secret"], "REDDIT_CLIENT_SECRET")
    if err:
        module.fail_json(msg=err)

    username, err = _resolve(module.params["username"], "REDDIT_USERNAME")
    if err:
        module.fail_json(msg=err)

    password, err = _resolve(module.params["password"], "REDDIT_PASSWORD")
    if err:
        module.fail_json(msg=err)

    subreddit, err = _resolve(module.params["subreddit"], "REDDIT_SUBREDDIT")
    if err:
        module.fail_json(msg=err)

    user_agent = module.params["user_agent"]
    if "/u/unknown" in user_agent:
        user_agent = f"ansible:social-poster:v1.0 (by /u/{username})"

    flair_id = module.params["flair_id"]

    result = dict(changed=False, post_id="", post_url="", response={})

    if module.check_mode:
        result["changed"] = True
        module.exit_json(**result)

    try:
        access_token, err = get_oauth_token(
            client_id, client_secret, username, password, user_agent
        )
        if err:
            module.fail_json(msg=err, **result)

        body, err = submit_post(
            access_token, user_agent, subreddit, title,
            text=text, url=url, flair_id=flair_id,
        )
        result["response"] = body

        if err:
            module.fail_json(msg=err, **result)

        json_data = body.get("json", {}).get("data", {})
        result["changed"] = True
        result["post_id"] = json_data.get("id", "")
        result["post_url"] = json_data.get("url", "")
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
