#!/usr/bin/python
"""
Ansible module to post to X (Twitter) via browser automation (Playwright).

No API keys required — uses a saved browser session from setup_x_session.py.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: x_post_browser
short_description: Post to X via browser automation
description:
  - Posts to X by driving a headless browser with a saved session.
  - Does not require paid API access.
  - Requires a one-time interactive login via setup_x_session.py.
options:
  text:
    description: The text content of the post (1-280 characters).
    required: true
    type: str
  session_file:
    description: Path to the saved session JSON file.
    required: false
    type: str
    default: ~/.x_ansible/session.json
  headless:
    description: Run the browser headlessly (set false for debugging).
    required: false
    type: bool
    default: true
  timeout:
    description: Max seconds to wait for page elements.
    required: false
    type: int
    default: 30
author:
  - Sean (@sean)
"""

EXAMPLES = r"""
- name: Post to X via browser
  x_post_browser:
    text: "Hello from Ansible!"

- name: Post with visible browser (for debugging)
  x_post_browser:
    text: "Testing..."
    headless: false
"""

RETURN = r"""
post_id:
  description: The ID of the created post (if captured from toast link).
  type: str
  returned: success
msg:
  description: Status message.
  type: str
  returned: always
"""

import json
import os
import re
import traceback
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

MAX_POST_LENGTH = 280

SELECTORS = {
    "compose_box": '[data-testid="tweetTextarea_0"]',
    "post_button": '[data-testid="tweetButton"]',
    "post_button_inline": '[data-testid="tweetButtonInline"]',
    "side_nav_post": '[data-testid="SideNav_NewTweet_Button"]',
    "toast": '[data-testid="toast"]',
}


def post_to_x(text, session_file, headless, timeout_sec):
    """Drive the browser to post. Returns (success, post_id, message)."""

    session_path = Path(session_file).expanduser()
    if not session_path.exists():
        return False, "", (
            f"Session file not found: {session_path}. "
            "Run 'python files/setup_x_session.py' first."
        )

    storage_state = json.loads(session_path.read_text())
    timeout_ms = timeout_sec * 1000

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        context.set_default_timeout(timeout_ms)
        page = context.new_page()

        # Navigate to the dedicated compose URL (more reliable than home feed)
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Check if we're still logged in
        if "login" in page.url.lower():
            browser.close()
            return False, "", (
                "Session expired — X redirected to login. "
                "Re-run 'python files/setup_x_session.py' to refresh."
            )

        # Wait for compose box
        try:
            page.wait_for_selector(
                SELECTORS["compose_box"], state="visible", timeout=timeout_ms
            )
        except Exception:
            browser.close()
            return False, "", (
                "Compose box not found. X may have changed their UI, "
                "or the session is invalid. Try re-running setup_x_session.py."
            )

        # Focus and insert text using execCommand (triggers React's input events)
        page.click(SELECTORS["compose_box"])
        page.wait_for_timeout(500)

        inserted = page.evaluate(
            """(text) => {
                const el = document.querySelector('[data-testid="tweetTextarea_0"]');
                if (!el) return false;
                el.focus();
                return document.execCommand('insertText', false, text);
            }""",
            text,
        )

        if not inserted:
            # Fallback: use fill() which dispatches input events
            page.fill(SELECTORS["compose_box"], text)

        page.wait_for_timeout(1000)

        # Click the post button via JS to bypass any overlay interception
        clicked = page.evaluate(
            """() => {
                const btn = document.querySelector('[data-testid="tweetButton"]');
                if (btn && !btn.disabled) { btn.click(); return true; }
                const btn2 = document.querySelector('[data-testid="tweetButtonInline"]');
                if (btn2 && !btn2.disabled) { btn2.click(); return true; }
                return false;
            }"""
        )

        if not clicked:
            browser.close()
            return False, "", (
                "Post button not found or was disabled. "
                "The text may not have been entered correctly."
            )

        # Wait for confirmation (toast notification or URL change)
        post_id = ""
        try:
            toast = page.wait_for_selector(
                SELECTORS["toast"], state="visible", timeout=10000
            )
            if toast:
                # Try to extract post ID from the "View" link in the toast
                page.wait_for_timeout(1000)
                link = toast.query_selector("a")
                if link:
                    href = link.get_attribute("href") or ""
                    match = re.search(r"/status/(\d+)", href)
                    if match:
                        post_id = match.group(1)
        except Exception:
            # Toast might not appear but post may have succeeded
            page.wait_for_timeout(3000)

        browser.close()
        return True, post_id, "Post published successfully."


def run_module():
    module_args = dict(
        text=dict(type="str", required=True),
        session_file=dict(type="str", default="~/.x_ansible/session.json"),
        headless=dict(type="bool", default=True),
        timeout=dict(type="int", default=30),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if not HAS_PLAYWRIGHT:
        module.fail_json(
            msg=(
                "The 'playwright' Python package is required. Install with: "
                "pip install playwright && playwright install chromium"
            )
        )

    text = module.params["text"].strip()
    if not text:
        module.fail_json(msg="'text' must not be empty or whitespace-only.")

    if len(text) > MAX_POST_LENGTH:
        module.fail_json(
            msg=f"Post text is {len(text)} characters; maximum is {MAX_POST_LENGTH}."
        )

    if module.check_mode:
        module.exit_json(changed=True, msg="Would post (check mode).", post_id="")

    try:
        success, post_id, message = post_to_x(
            text=text,
            session_file=module.params["session_file"],
            headless=module.params["headless"],
            timeout_sec=module.params["timeout"],
        )

        if success:
            module.exit_json(changed=True, post_id=post_id, msg=message)
        else:
            module.fail_json(msg=message, post_id="")

    except Exception:
        module.fail_json(msg=f"Unhandled exception: {traceback.format_exc()}")


def main():
    run_module()


if __name__ == "__main__":
    main()
