# AI (Claude via MAAS)

Generate platform-specific social media posts with Claude Haiku. Produces tailored versions for LinkedIn, Bluesky, and X, previews them all, then optionally publishes.

## Overview

- **Endpoint:** `https://maas-rhdp.apps.maas.redhatworkshops.io/v1/chat/completions`
- **Model:** `claude-haiku-4-5` (OpenAI-compatible chat completions format)
- **Auth:** Bearer token via `MAAS` environment variable
- **Method:** Pure Ansible `uri` module — no Python SDK needed

## Setup

```bash
export MAAS="your-maas-api-key"
```

That's it. No billing accounts, no OAuth flows, no extra Python packages.

## Usage

### Preview posts for all platforms (default)

```bash
ansible-playbook ai/generate_post.yml -e 'content="I just shipped a new Ansible collection"'
```

This generates three separate posts — one optimized for each platform — and displays them side-by-side with character counts. Nothing gets published.

### Preview + publish to all platforms

```bash
ansible-playbook ai/generate_post.yml -e 'content="..." publish=true'
```

### Preview + publish to a single platform

```bash
ansible-playbook ai/generate_post.yml -e 'content="..." publish=true platform=linkedin'
```

### Include a URL

```bash
ansible-playbook ai/generate_post.yml \
  -e 'content="Check out this demo" url="https://youtube.com/..."'
```

### Override the tone

```bash
ansible-playbook ai/generate_post.yml \
  -e 'content="Fixed a nasty bug" tone="excited and celebratory"'
```

### Use a different model

```bash
ansible-playbook ai/generate_post.yml -e 'content="..." model=claude-sonnet-4'
```

## Parameters

| Variable | Required | Default | Description |
|---|---|---|---|
| `content` | Yes | — | What you want to post about |
| `publish` | No | `false` | Set to `true` to actually publish |
| `platform` | No | `all` | Which platforms to generate for: `linkedin`, `bluesky`, `x`, or `all` |
| `url` | No | — | URL to include as context in the prompt |
| `tone` | No | — | Override writing tone (e.g. "casual", "professional", "excited") |
| `model` | No | `claude-haiku-4-5` | Model to use |
| `max_tokens` | No | `1024` | Max output tokens per generation |

## How it works

1. Makes **3 separate API calls** to Claude — one per platform with tailored constraints:
   - **LinkedIn:** Up to 3000 chars, professional but personable
   - **Bluesky:** Up to 300 chars, short and punchy
   - **X (Twitter):** Up to 280 chars, extremely concise
2. Displays all three versions in a formatted preview with character counts
3. If `publish=true`, publishes each post to its respective platform using the existing posting modules

## Example output

```
╔═══════════════════════════════════════════════════════════╗
║  GENERATED POSTS (model: claude-haiku-4-5)
║  publish=false
╚═══════════════════════════════════════════════════════════╝

┌─── LinkedIn ────────────────────────────────────────────┐

Just shipped automated network config backups using Ansible.
No more manual snapshots, no more "did someone save that?"

The whole thing runs on a cron job and pushes to git.
If you're managing network gear, this saves hours.

#NetworkAutomation #Ansible

└─────────────────────────────────────── (248 chars) ┘

┌─── Bluesky ─────────────────────────────────────────────┐

Automated my network config backups with Ansible — runs on
cron, pushes to git. No more manual snapshots ever again.

└─────────────────────────────────────── (132 chars) ┘

┌─── X (Twitter) ─────────────────────────────────────────┐

Automated network config backups with Ansible + git. Never
doing manual snapshots again. #NetworkAutomation

└─────────────────────────────────────── (119 chars) ┘
```

## File structure

```
ai/
├── generate_post.yml      # Main playbook
├── tasks/
│   └── ask_ai.yml         # Reusable task (call any OpenAI-compatible endpoint)
└── README.md
```

## Reusing `tasks/ask_ai.yml`

The task file is generic and works with any OpenAI-compatible API. Set these variables before including it:

```yaml
- name: Set up AI call
  ansible.builtin.set_fact:
    ai_api_url: "https://your-endpoint/v1/chat/completions"
    ai_api_key: "{{ lookup('env', 'YOUR_KEY') }}"
    ai_model: "your-model-name"
    ai_prompt: "Your prompt here"
    ai_max_tokens: 512

- name: Call AI
  ansible.builtin.include_tasks: ai/tasks/ask_ai.yml

- name: Use the result
  ansible.builtin.debug:
    msg: "{{ ai_result.response }}"
```

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `MAAS environment variable is not set` | `MAAS` not exported | `export MAAS="your-key"` |
| `401 Unauthorized` | Invalid or expired key | Get a new key from MAAS admin |
| `429 Too Many Requests` | Rate limited | Wait and retry, or reduce frequency |
| `503 Service Unavailable` | MAAS endpoint down | Try again later |
| `404 Not Found` (model) | Model name wrong | Check available models on the endpoint |

## Notes

- The MAAS endpoint is OpenAI-compatible, so any tooling that works with OpenAI's chat completions format will work here.
- Any model available on the MAAS endpoint can be used via `-e 'model=...'`.
- Default behavior is **preview only** — you must explicitly pass `publish=true` to post anything live.
