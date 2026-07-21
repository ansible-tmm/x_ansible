#!/usr/bin/python
"""
Ansible module to publish a post to Bluesky via the AT Protocol API.

Authentication: App Password (created in Bluesky settings)
Endpoint:      POST https://bsky.social/xrpc/com.atproto.repo.createRecord
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: bluesky_post
short_description: Post a message to Bluesky
version_added: "1.0.0"
description:
  - Publishes a text post to Bluesky using the AT Protocol API.
  - Uses App Password authentication (free, no paid tier required).
  - Posting is inherently non-idempotent; every successful run creates a new post.
options:
  text:
    description: The text content of the post (1-300 characters).
    required: true
    type: str
  handle:
    description: >-
      Your Bluesky handle (e.g. yourname.bsky.social).
      Falls back to BLUESKY_HANDLE env var.
    required: false
    type: str
  app_password:
    description: >-
      Bluesky App Password (NOT your main password).
      Falls back to BLUESKY_APP_PASSWORD env var.
    required: false
    type: str
  pds_url:
    description: Personal Data Server URL.
    required: false
    type: str
    default: https://bsky.social
author:
  - Sean (@sean)
"""

EXAMPLES = r"""
- name: Post to Bluesky using environment variables
  bluesky_post:
    text: "Hello from Ansible!"

- name: Post with explicit credentials (use Vault in practice)
  bluesky_post:
    text: "{{ post_text }}"
    handle: "{{ vault_bluesky_handle }}"
    app_password: "{{ vault_bluesky_app_password }}"
"""

RETURN = r"""
uri:
  description: The AT URI of the created post.
  type: str
  returned: success
cid:
  description: The content hash (CID) of the created post.
  type: str
  returned: success
response:
  description: The full JSON response body from the API.
  type: dict
  returned: always
"""

import json
import os
import re
import traceback
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

from ansible.module_utils.basic import AnsibleModule

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

MAX_POST_LENGTH = 300


def _resolve(module_param, env_var_name):
    """Return the module parameter if set, otherwise the environment variable."""
    value = module_param or os.environ.get(env_var_name)
    if not value:
        return None, (
            f"Missing: provide '{env_var_name.lower()}' parameter "
            f"or set the {env_var_name} environment variable."
        )
    return value, None


def create_session(pds_url, handle, app_password):
    """Authenticate and return (session_dict, error_msg)."""
    resp = requests.post(
        f"{pds_url}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=15,
    )

    if resp.status_code == 200:
        return resp.json(), None
    elif resp.status_code == 401:
        return None, (
            "Authentication failed (401). Check your handle and app password. "
            "Make sure you're using an App Password, not your main password."
        )
    elif resp.status_code == 429:
        return None, "Rate limited (429). Wait a moment and try again."
    else:
        body = resp.text
        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError):
            pass
        return None, f"Session creation failed (HTTP {resp.status_code}): {body}"


def parse_facets(text):
    """Detect URLs in text and return Bluesky facets for clickable links.

    Bluesky requires explicit facets with byte offsets to make links clickable.
    """
    facets = []
    url_pattern = re.compile(
        r'https?://[^\s\)\]\}>,;"\']+',
        re.IGNORECASE,
    )
    text_bytes = text.encode("utf-8")

    for match in url_pattern.finditer(text):
        url = match.group(0)
        # Strip trailing punctuation that's likely not part of the URL
        while url and url[-1] in ".,;:!?)":
            url = url[:-1]

        start_char = match.start()
        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = byte_start + len(url.encode("utf-8"))

        facets.append({
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": url,
                }
            ],
        })

    return facets


class OGParser(HTMLParser):
    """Minimal HTML parser to extract OpenGraph meta tags."""

    def __init__(self):
        super().__init__()
        self.og = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            attr_dict = dict(attrs)
            prop = attr_dict.get("property", "") or attr_dict.get("name", "")
            content = attr_dict.get("content", "")
            if prop.startswith("og:") and content:
                self.og[prop[3:]] = content

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def fetch_link_card(url):
    """Fetch OpenGraph metadata from a URL. Returns dict with title, description, image_url or None."""
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BlueSkyBot/1.0)"},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception:
        return None

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type:
        return None

    parser = OGParser()
    try:
        parser.feed(resp.text[:50000])
    except Exception:
        return None

    title = parser.og.get("title", "") or parser.title.strip()
    description = parser.og.get("description", "")
    image_url = parser.og.get("image", "")

    if not title:
        return None

    if image_url and "://" not in image_url:
        image_url = urljoin(url, image_url)

    return {
        "uri": url,
        "title": title[:300],
        "description": description[:1000],
        "image_url": image_url,
    }


def upload_blob(pds_url, session, image_url):
    """Download an image and upload it to Bluesky as a blob. Returns blob ref or None."""
    try:
        img_resp = requests.get(
            image_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BlueSkyBot/1.0)"},
        )
        img_resp.raise_for_status()
    except Exception:
        return None

    content_type = img_resp.headers.get("content-type", "image/jpeg")
    img_data = img_resp.content

    # Bluesky blob limit is 1MB
    if len(img_data) > 1_000_000:
        return None

    try:
        blob_resp = requests.post(
            f"{pds_url}/xrpc/com.atproto.repo.uploadBlob",
            headers={
                "Authorization": f"Bearer {session['accessJwt']}",
                "Content-Type": content_type,
            },
            data=img_data,
            timeout=15,
        )
        blob_resp.raise_for_status()
        return blob_resp.json().get("blob")
    except Exception:
        return None


def build_embed(pds_url, session, text):
    """Detect the first URL in text and build an external embed with link card."""
    url_pattern = re.compile(r'https?://[^\s\)\]\}>,;"\']+', re.IGNORECASE)
    match = url_pattern.search(text)
    if not match:
        return None

    url = match.group(0)
    while url and url[-1] in ".,;:!?)":
        url = url[:-1]

    card = fetch_link_card(url)
    if not card:
        return None

    external = {
        "uri": card["uri"],
        "title": card["title"],
        "description": card["description"],
    }

    if card.get("image_url"):
        blob = upload_blob(pds_url, session, card["image_url"])
        if blob:
            external["thumb"] = blob

    return {
        "$type": "app.bsky.embed.external",
        "external": external,
    }


def create_post(pds_url, session, text):
    """Create a post and return (response_dict, error_msg)."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
    }

    facets = parse_facets(text)
    if facets:
        record["facets"] = facets

    embed = build_embed(pds_url, session, text)
    if embed:
        record["embed"] = embed

    resp = requests.post(
        f"{pds_url}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        json={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=15,
    )

    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        body = {"raw": resp.text}

    if resp.status_code == 200:
        return body, None
    elif resp.status_code == 401:
        return body, "Post failed (401). Session may have expired."
    elif resp.status_code == 429:
        return body, "Rate limited (429). Wait and retry."
    else:
        return body, f"Post failed (HTTP {resp.status_code}): {body}"


def run_module():
    module_args = dict(
        text=dict(type="str", required=True),
        handle=dict(type="str", required=False, default=None),
        app_password=dict(type="str", required=False, default=None, no_log=True),
        pds_url=dict(type="str", default="https://bsky.social"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if not HAS_REQUESTS:
        module.fail_json(msg="The 'requests' Python package is required.")

    text = module.params["text"].strip()
    if not text:
        module.fail_json(msg="'text' must not be empty or whitespace-only.")

    if len(text) > MAX_POST_LENGTH:
        module.fail_json(
            msg=f"Post text is {len(text)} characters; Bluesky maximum is {MAX_POST_LENGTH}."
        )

    handle, err = _resolve(module.params["handle"], "BLUESKY_HANDLE")
    if err:
        module.fail_json(msg=err)

    app_password, err = _resolve(module.params["app_password"], "BLUESKY_APP_PASSWORD")
    if err:
        module.fail_json(msg=err)

    pds_url = module.params["pds_url"].rstrip("/")

    result = dict(changed=False, uri="", cid="", response={})

    if module.check_mode:
        result["changed"] = True
        module.exit_json(**result)

    try:
        session, err = create_session(pds_url, handle, app_password)
        if err:
            module.fail_json(msg=err, **result)

        body, err = create_post(pds_url, session, text)
        result["response"] = body

        if err:
            module.fail_json(msg=err, **result)

        result["changed"] = True
        result["uri"] = body.get("uri", "")
        result["cid"] = body.get("cid", "")
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
