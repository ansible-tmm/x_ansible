# LinkedIn

Post messages to your LinkedIn personal profile from Ansible using the Posts API.

## Overview

- **Cost:** Free (no paid tier for personal posting)
- **Auth:** OAuth 2.0 bearer token
- **Token lifetime:** 60 days (then re-run setup)
- **Max post length:** 3,000 characters
- **Rate limit:** 150 posts/day per member
- **Works from:** Any machine, any IP

## Files

| File | Purpose |
|---|---|
| `library/linkedin_post.py` | Custom Ansible module |
| `files/setup_linkedin_token.py` | One-time OAuth setup script |
| `post_to_linkedin.yml` | Playbook |
| `vars/credentials_example.yml` | Vault template |

## Prerequisites

You need a LinkedIn developer app. One-time setup (~15 minutes):

1. Go to [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps)
2. Create an app (requires a LinkedIn Company Page — any page you admin works)
3. On the **Settings** tab, click **Verify** to link the app to your page
   - Generate the verification URL and open it yourself (you're the page admin)
4. On the **Products** tab, enable:
   - **Share on LinkedIn** (grants `w_member_social` — instant, no review)
   - **Sign In with LinkedIn using OpenID Connect** (grants `openid profile email` — instant)
5. On the **Auth** tab:
   - Copy your **Client ID** and **Client Secret**
   - Add `http://localhost:8000/callback` to **Authorized redirect URLs**

## Setup

### Run the OAuth setup script

```bash
source venv/bin/activate
export LINKEDIN_CLIENT_ID="your-client-id"
export LINKEDIN_CLIENT_SECRET="your-client-secret"
python linkedin/files/setup_linkedin_token.py
```

This will:
1. Open your browser to LinkedIn's authorization page
2. You click "Allow"
3. LinkedIn redirects back to localhost
4. The script exchanges the code for an access token
5. Fetches your person URN (member ID)
6. Saves everything to `~/.x_ansible/linkedin.json`

After setup, no environment variables are needed — the module reads from the
saved config file automatically.

## Usage

```bash
source venv/bin/activate
ansible-playbook linkedin/post_to_linkedin.yml -e 'post_text=hello from ansible'
```

### Check mode (dry run)

```bash
ansible-playbook linkedin/post_to_linkedin.yml -e 'post_text=test' --check
```

### With Ansible Vault

```bash
cp vars/credentials_example.yml vars/credentials.yml
# Edit with real values
ansible-vault encrypt vars/credentials.yml
```

Then uncomment the `vars_files` and credential lines in `post_to_linkedin.yml`.

## Module parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `text` | Yes | — | Post text (1-3000 characters) |
| `access_token` | No | env/config file | OAuth 2.0 access token |
| `person_urn` | No | env/config file | Your person URN (e.g. `urn:li:person:abc123`) |
| `visibility` | No | `PUBLIC` | Post visibility (`PUBLIC` or `CONNECTIONS`) |
| `api_version` | No | `202607` | LinkedIn API version (YYYYMM format) |

### Credential resolution order

The module resolves `access_token` and `person_urn` in this order:
1. Module parameter (for Vault usage)
2. Environment variable (`LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN`)
3. Config file (`~/.x_ansible/linkedin.json`)

## Return values

| Field | Description |
|---|---|
| `post_urn` | URN of the created post (from `x-restli-id` header) |
| `response_status` | HTTP status code |
| `response_body` | Response body (empty on success, JSON on error) |

## Token refresh

The access token expires every **60 days**. When you get a 401 error, re-run:

```bash
export LINKEDIN_CLIENT_ID="your-client-id"
export LINKEDIN_CLIENT_SECRET="your-client-secret"
python linkedin/files/setup_linkedin_token.py
```

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| 401 Unauthorized | Token expired (60-day limit) | Re-run `setup_linkedin_token.py` |
| 403 Forbidden | Missing `w_member_social` scope | Enable "Share on LinkedIn" in developer portal |
| 426 NONEXISTENT_VERSION | API version expired | Update `api_version` parameter in the module |
| 429 Rate limited | Over 150 posts/day | Wait, reduce posting frequency |
| "Missing" credential error | Config file not found | Run the setup script |
| Browser doesn't open | Port 8000 in use | Kill the process on port 8000 and retry |

## Notes

- Posts appear on your **personal profile** feed, not the Company Page.
- The Company Page is only needed to create the developer app.
- Posting is non-idempotent: running twice = two posts.
- Supports `--check` mode (validates without posting).
- The `visibility` parameter controls who sees the post (public vs connections only).
