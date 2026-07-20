# Bluesky

Post messages to Bluesky from Ansible using the AT Protocol API.

## Overview

- **Cost:** Free, no paid tier
- **Auth:** App Password (never expires)
- **Max post length:** 300 characters
- **Rate limit:** 5,000 points/hour
- **Works from:** Any machine, any IP

## Files

| File | Purpose |
|---|---|
| `library/bluesky_post.py` | Custom Ansible module |
| `post_to_bluesky.yml` | Playbook |
| `vars/credentials_example.yml` | Vault template |

## Setup

### 1. Create an App Password

1. Go to [Bluesky Settings → App Passwords](https://bsky.app/settings/app-passwords)
2. Click "Add App Password"
3. Name it (e.g. "ansible")
4. Copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`)

### 2. Set environment variables

```bash
export BLUESKY_HANDLE="yourname.bsky.social"
export BLUESKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

Or put them in a `.env` file (gitignored) and `source .env`.

## Usage

```bash
source venv/bin/activate
ansible-playbook bluesky/post_to_bluesky.yml -e 'post_text=hello from ansible'
```

### Check mode (dry run)

```bash
ansible-playbook bluesky/post_to_bluesky.yml -e 'post_text=test' --check
```

### With Ansible Vault

```bash
cp vars/credentials_example.yml vars/credentials.yml
# Edit with real values
ansible-vault encrypt vars/credentials.yml
```

Then uncomment the `vars_files` and credential lines in `post_to_bluesky.yml`:

```bash
ansible-playbook bluesky/post_to_bluesky.yml -e 'post_text=hello' --ask-vault-pass
```

## Module parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `text` | Yes | — | Post text (1-300 characters) |
| `handle` | No | env `BLUESKY_HANDLE` | Your Bluesky handle |
| `app_password` | No | env `BLUESKY_APP_PASSWORD` | App Password (not your main password) |
| `pds_url` | No | `https://bsky.social` | Personal Data Server URL |

## Return values

| Field | Description |
|---|---|
| `uri` | AT URI of the created post |
| `cid` | Content hash (CID) of the post |
| `response` | Full JSON response from the API |

## How it works

1. Authenticates via `com.atproto.server.createSession` (handle + app password → JWT)
2. Creates the post via `com.atproto.repo.createRecord`
3. Returns the post URI and CID

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| 401 Unauthorized | Bad handle or app password | Check handle format (include `.bsky.social`), regenerate app password |
| 429 Rate limited | Too many requests | Wait a few minutes |
| Connection error | Network issue or wrong PDS URL | Check connectivity |
| Text too long | Over 300 characters | Shorten the text |
| Empty text | Forgot `-e 'post_text=...'` | Always provide post_text |

## Notes

- App passwords never expire — no refresh needed.
- Posting is non-idempotent: running twice = two posts.
- The module validates text length before calling the API.
- Supports `--check` mode (validates without posting).
