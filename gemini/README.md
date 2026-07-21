# Gemini

Generate social media posts with Google Gemini, then optionally publish them.

## Overview

- **Cost:** Free (Gemini API has a generous free tier)
- **Auth:** `GOOGLE_API_KEY` environment variable
- **Method:** Pure Ansible `uri` module — no Python SDK needed
- **Pattern:** Gemini generates the post text → deterministic Ansible tasks publish it

## Flow

```
Content/idea (you)
    ↓
Gemini generates polished post text
    ↓
Ansible publishes to LinkedIn / Bluesky / X (or just prints it)
```

One playbook, two steps: AI generates, automation posts. No MCP, no wasted tokens
on tool-calling loops.

## Files

| File | Purpose |
|---|---|
| `tasks/ask_gemini.yml` | Reusable task file — sends prompt, stores response |
| `generate_post.yml` | Main playbook — builds prompt, calls Gemini, optionally publishes |

## Setup

You just need a Google API key:

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create an API key
3. Export it:

```bash
export GOOGLE_API_KEY="your-api-key"
```

## Usage

### Generate a post (preview only)

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="I just released a new Ansible collection for network automation"'
```

This prints the generated post but does not publish it.

### Generate and publish to LinkedIn

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="Just shipped a new feature for automated config backups" platform=linkedin'
```

### Generate and publish to Bluesky

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="Playing with browser automation in Ansible" platform=bluesky'
```

### Generate and publish to all platforms

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="Big update to my automation toolkit" platform=all'
```

### Include a URL (video, blog, demo)

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="Check out this demo of posting from Ansible" url="https://youtube.com/watch?v=..." platform=linkedin'
```

### Override the tone

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="Shipped a bugfix" platform=linkedin tone="casual and fun"'
```

### Use a different model

```bash
ansible-playbook gemini/generate_post.yml \
  -e 'content="..." model=gemini-2.5-pro'
```

## Parameters

| Variable | Required | Default | Description |
|---|---|---|---|
| `content` | Yes | — | What you want to post about (description, context, notes) |
| `platform` | No | `none` | Target: `linkedin`, `bluesky`, `x`, `all`, or `none` (preview only) |
| `url` | No | — | URL to include as context (video, blog, link) |
| `tone` | No | — | Override the writing tone (e.g. "casual", "technical", "excited") |
| `model` | No | `gemini-2.5-flash` | Gemini model to use |
| `max_tokens` | No | `1024` | Max output tokens |

## How it works

1. **Prompt construction** — builds a system prompt with platform-specific rules
   (character limits, tone guidance) plus your content
2. **Gemini API call** — `POST` to `generativelanguage.googleapis.com` via
   `ansible.builtin.uri` (no Python dependencies beyond `requests`)
3. **Response parsing** — extracts `candidates[0].content.parts[0].text`
4. **Publishing** — if `platform` is set, passes the generated text directly
   to the appropriate posting module (`linkedin_post`, `bluesky_post`, etc.)

## Platform character limits

The prompt automatically instructs Gemini to respect these limits:

| Platform | Max length |
|---|---|
| LinkedIn | 3,000 characters |
| Bluesky | 300 characters |
| X (Twitter) | 280 characters |
| General (no platform specified) | 280 characters |

## Reusing `tasks/ask_gemini.yml` in other playbooks

The task file is generic — you can include it from any playbook:

```yaml
vars:
  gemini_api_key: "{{ lookup('ansible.builtin.env', 'GOOGLE_API_KEY') }}"
  gemini_model: "gemini-2.5-flash"
  gemini_max_tokens: 1024
  gemini_api_url: "https://generativelanguage.googleapis.com/v1beta/models/{{ gemini_model }}:generateContent"

tasks:
  - name: Build your prompt
    ansible.builtin.set_fact:
      gemini_prompt: "Your custom prompt here..."

  - name: Call Gemini
    ansible.builtin.include_tasks: path/to/gemini/tasks/ask_gemini.yml

  - name: Use the result
    ansible.builtin.debug:
      msg: "{{ gemini_result.response }}"
```

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| 401 Unauthorized | Bad API key | Check `GOOGLE_API_KEY` value |
| 403 Forbidden | API key doesn't have Generative Language API enabled | Enable it in Google Cloud Console |
| 429 Rate limited | Too many requests | Wait, or switch to a paid tier |
| "GOOGLE_API_KEY not set" | Env var missing | `export GOOGLE_API_KEY="..."` |
| Post too long for platform | Gemini occasionally exceeds limits | Re-run, or manually trim |

## Notes

- The AI generation and the posting are separate steps — if generation succeeds
  but posting fails, you can see the generated text in the output and post manually.
- `no_log: true` is set on the API call to prevent your key from appearing in logs.
- Token usage (prompt + output) is displayed after each generation.
- This uses zero Python SDK dependencies — pure REST via Ansible's `uri` module.
