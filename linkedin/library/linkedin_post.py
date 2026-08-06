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
import re
import traceback
from html.parser import HTMLParser
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


class OGParser(HTMLParser):
    """Parse OpenGraph and standard meta tags from HTML."""

    def __init__(self):
        super().__init__()
        self.og = {}
        self.meta = {}
        self._title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            attrs_dict = dict(attrs)
            prop = attrs_dict.get("property", "")
            name = attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            if prop.startswith("og:") and content:
                self.og[prop[3:]] = content
            elif name and content:
                self.meta[name] = content
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self._title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def get_title(self):
        return self.og.get("title") or self.meta.get("title") or self._title.strip()

    def get_description(self):
        return self.og.get("description") or self.meta.get("description") or ""


def fetch_og_metadata(url):
    """Fetch title and description from a URL using oEmbed, OG tags, or meta tags."""
    try:
        # oEmbed first for YouTube (their HTML is too large to parse efficiently)
        if "youtu.be" in url or "youtube.com" in url:
            oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
            try:
                oembed = requests.get(oembed_url, timeout=5)
                if oembed.status_code == 200:
                    data = oembed.json()
                    return data.get("title"), data.get("author_name", "")
            except Exception:
                pass

        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            },
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None, None

        html = resp.text[:200000]
        title = None
        desc = None

        # Try HTMLParser
        parser = OGParser()
        try:
            parser.feed(html)
        except Exception:
            pass
        title = parser.get_title()
        desc = parser.get_description()

        # Regex fallback for meta tags
        if not title:
            m = re.search(
                r'<meta\s+(?:property|name)=["\'](?:og:title|title)["\']\s+content=["\']([^"\']+)["\']',
                html,
            ) or re.search(
                r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\'](?:og:title|title)["\']',
                html,
            )
            if m:
                title = m.group(1)

        if not desc:
            m = re.search(
                r'<meta\s+(?:property|name)=["\'](?:og:description|description)["\']\s+content=["\']([^"\']+)["\']',
                html,
            ) or re.search(
                r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\'](?:og:description|description)["\']',
                html,
            )
            if m:
                desc = m.group(1)

        if not title:
            m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
            if m:
                title = m.group(1).strip()

        return title or None, desc or None
    except Exception:
        return None, None


def fetch_thumbnail_url(url):
    """Get the thumbnail/og:image URL for a given page."""
    try:
        # YouTube oEmbed provides thumbnail_url
        if "youtu.be" in url or "youtube.com" in url:
            oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
            resp = requests.get(oembed_url, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("thumbnail_url")

        # For other sites, fetch og:image
        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            },
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        html = resp.text[:200000]
        m = re.search(
            r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
            html,
        ) or re.search(
            r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']',
            html,
        )
        return m.group(1) if m else None
    except Exception:
        return None


def upload_thumbnail_to_linkedin(image_url, person_urn, access_token, api_version):
    """Download an image and upload it to LinkedIn's Images API. Returns image URN or None."""
    try:
        # Download the image
        img_resp = requests.get(image_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0"
        })
        if img_resp.status_code != 200:
            return None

        image_data = img_resp.content
        content_type = img_resp.headers.get("Content-Type", "image/jpeg")

        # Initialize upload
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": api_version,
        }
        init_resp = requests.post(
            "https://api.linkedin.com/rest/images?action=initializeUpload",
            headers=headers,
            json={"initializeUploadRequest": {"owner": person_urn}},
            timeout=10,
        )
        if init_resp.status_code != 200:
            return None

        init_data = init_resp.json().get("value", {})
        upload_url = init_data.get("uploadUrl")
        image_urn = init_data.get("image")
        if not upload_url or not image_urn:
            return None

        # Upload the binary image
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type,
        }
        upload_resp = requests.put(
            upload_url,
            headers=upload_headers,
            data=image_data,
            timeout=15,
        )
        if upload_resp.status_code in (200, 201):
            return image_urn
        return None
    except Exception:
        return None


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
        # Note: We intentionally do NOT attach the URL as content.article.
        # When the URL is in the post text, LinkedIn auto-generates a full-width
        # rich media preview card (the large thumbnail you see in the web UI).
        # Explicitly attaching it as content.article creates a smaller card instead.

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
