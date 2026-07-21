#!/usr/bin/env python3
"""Social media post generator web UI.

Run with:
    cd x_ansible
    source venv/bin/activate
    python webapp/app.py
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
ANSIBLE_PLAYBOOK = PROJECT_ROOT / "venv" / "bin" / "ansible-playbook"

PLATFORM_PLAYBOOKS = {
    "linkedin": PROJECT_ROOT / "linkedin" / "post_to_linkedin.yml",
    "bluesky": PROJECT_ROOT / "bluesky" / "post_to_bluesky.yml",
    "x": PROJECT_ROOT / "x" / "post_to_x_browser.yml",
    "reddit": PROJECT_ROOT / "reddit" / "post_to_reddit.yml",
    "threads": PROJECT_ROOT / "threads" / "post_to_threads.yml",
}


def run_ansible(playbook: str, extra_vars: dict, timeout: int = 120) -> tuple[bool, str]:
    """Run an ansible-playbook command and return (success, output)."""
    cmd = [
        str(ANSIBLE_PLAYBOOK),
        str(playbook),
        "--extra-vars", json.dumps(extra_vars),
    ]

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env["ANSIBLE_FORCE_COLOR"] = "0"
    env["ANSIBLE_LOCAL_TEMP"] = str(PROJECT_ROOT / ".ansible_tmp")
    env["ANSIBLE_REMOTE_TEMP"] = str(PROJECT_ROOT / ".ansible_tmp")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Playbook timed out"
    except Exception as e:
        return False, str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    content = data.get("content", "").strip()
    url = data.get("url", "").strip()
    tone = data.get("tone", "").strip()
    system_prompts = data.get("system_prompts", {})

    if not content:
        return jsonify({"error": "Content is required"}), 400

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_file = f.name

    extra_vars = {
        "content": content,
        "output_file": output_file,
    }
    if url:
        extra_vars["url"] = url
    if tone:
        extra_vars["tone"] = tone
    if system_prompts.get("linkedin"):
        extra_vars["system_prompt_linkedin"] = system_prompts["linkedin"]
    if system_prompts.get("bluesky"):
        extra_vars["system_prompt_bluesky"] = system_prompts["bluesky"]
    if system_prompts.get("x"):
        extra_vars["system_prompt_x"] = system_prompts["x"]
    if system_prompts.get("reddit"):
        extra_vars["system_prompt_reddit"] = system_prompts["reddit"]
    if system_prompts.get("threads"):
        extra_vars["system_prompt_threads"] = system_prompts["threads"]

    playbook = PROJECT_ROOT / "webapp" / "generate_only.yml"
    success, output = run_ansible(playbook, extra_vars)

    if not success:
        try:
            os.unlink(output_file)
        except OSError:
            pass
        return jsonify({"error": "Generation failed", "details": output}), 500

    try:
        with open(output_file) as f:
            posts = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return jsonify({"error": f"Failed to read generated posts: {e}"}), 500
    finally:
        try:
            os.unlink(output_file)
        except OSError:
            pass

    return jsonify(posts)


@app.route("/publish", methods=["POST"])
def publish():
    data = request.get_json()
    platform = data.get("platform", "")
    text = data.get("text", "").strip()

    if platform not in PLATFORM_PLAYBOOKS:
        return jsonify({"error": f"Unknown platform: {platform}"}), 400
    if not text:
        return jsonify({"error": "Post text is required"}), 400

    playbook = PLATFORM_PLAYBOOKS[platform]

    if platform == "reddit":
        reddit_title = data.get("reddit_title", "").strip()
        reddit_url = data.get("reddit_url", "").strip()
        reddit_subreddit = data.get("reddit_subreddit", "").strip()
        if not reddit_title:
            return jsonify({"error": "Reddit requires a title"}), 400
        extra_vars = {"title": reddit_title, "subreddit": reddit_subreddit}
        if reddit_url:
            extra_vars["url"] = reddit_url
        else:
            extra_vars["text"] = text
    elif platform == "linkedin":
        extra_vars = {"post_text": text}
        url_match = re.search(r'https?://[^\s)}\]>,;"\']+', text)
        if url_match:
            extra_vars["url"] = url_match.group(0)
    else:
        extra_vars = {"post_text": text}

    success, output = run_ansible(playbook, extra_vars, timeout=60)

    if success:
        post_url = _extract_post_url(platform, output)
        return jsonify({"success": True, "platform": platform, "post_url": post_url})
    else:
        return jsonify({"error": f"Publishing to {platform} failed", "details": output}), 500


def _extract_post_url(platform, output):
    """Extract the published post URL from Ansible debug output."""
    if platform == "linkedin":
        match = re.search(r"post_urn['\"]?:\s*['\"]?(urn:li:\w+:\d+)", output)
        if match:
            return f"https://www.linkedin.com/feed/update/{match.group(1)}"
    elif platform == "bluesky":
        match = re.search(r"uri['\"]?:\s*['\"]?(at://[^\s'\"]+)", output)
        if match:
            uri = match.group(1)
            parts = uri.replace("at://", "").split("/")
            if len(parts) >= 3:
                did = parts[0]
                rkey = parts[2]
                return f"https://bsky.app/profile/{did}/post/{rkey}"
    elif platform == "x":
        match = re.search(r"post_id['\"]?:\s*['\"]?(\d+)", output)
        if match:
            return f"https://x.com/i/status/{match.group(1)}"
    elif platform == "reddit":
        match = re.search(r"https://(?:www\.)?reddit\.com/[^\s'\"]+", output)
        if match:
            return match.group(0).rstrip("'\"")
    elif platform == "threads":
        match = re.search(r"https://(?:www\.)?threads\.net/[^\s'\"]+", output)
        if match:
            return match.group(0).rstrip("'\"")
        # Fallback: construct from post_id
        post_id_match = re.search(r"Post ID:\s*(\d+)", output)
        if post_id_match:
            return f"https://www.threads.net/post/{post_id_match.group(1)}"
    return ""


if __name__ == "__main__":
    print(f"\n  Social Media Post Generator")
    print(f"  http://127.0.0.1:5001\n")
    app.run(host="127.0.0.1", port=5001, debug=True)
