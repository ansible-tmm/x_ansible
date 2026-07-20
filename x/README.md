# X (Twitter)

Post messages to X from Ansible. Two approaches available:

1. **Official API** (`x_post`) — requires a paid plan (~$200+/month)
2. **Browser automation** (`x_post_browser`) — free, uses Playwright with saved cookies

## Overview

| | Official API | Browser Automation |
|---|---|---|
| **Cost** | ~$200+/month | Free |
| **Auth** | OAuth 1.0a (4 keys) | Browser session cookies |
| **Reliability** | High | Can break when X changes UI |
| **TOS** | Compliant | Technically violates TOS |
| **Speed** | ~1 second | 5-10 seconds |
| **Works from** | Any machine | Same IP as session origin |

## Files

| File | Purpose |
|---|---|
| `library/x_post.py` | Module — official API (paid) |
| `library/x_post_browser.py` | Module — browser automation (free) |
| `files/setup_x_session.py` | One-time cookie extraction script |
| `post_to_x.yml` | Playbook — official API |
| `post_to_x_browser.yml` | Playbook — browser automation |
| `post_to_x_uri.yml` | Playbook — alternative (uri-based) |
| `vars/credentials_example.yml` | Vault template (API approach) |

---

## Option 1: Official API (paid)

As of February 2026, X eliminated free API access. You need a paid plan.

### Setup

1. Get a paid X API plan at [developer.x.com](https://developer.x.com)
2. Create a Project and App with **Read and Write** permissions
3. Generate API keys and access tokens (**after** enabling write)

### Environment variables

```bash
export X_API_KEY="your-api-key"
export X_API_SECRET="your-api-key-secret"
export X_ACCESS_TOKEN="your-access-token"
export X_ACCESS_TOKEN_SECRET="your-access-token-secret"
```

### Usage

```bash
source venv/bin/activate
ansible-playbook x/post_to_x.yml -e 'post_text=hello from ansible'
```

### Module parameters (`x_post`)

| Parameter | Required | Default | Description |
|---|---|---|---|
| `text` | Yes | — | Post text (1-280 characters) |
| `api_key` | No | env `X_API_KEY` | API Key (Consumer Key) |
| `api_secret` | No | env `X_API_SECRET` | API Secret (Consumer Secret) |
| `access_token` | No | env `X_ACCESS_TOKEN` | OAuth 1.0a Access Token |
| `access_token_secret` | No | env `X_ACCESS_TOKEN_SECRET` | OAuth 1.0a Access Token Secret |

### Why 4 keys?

OAuth 1.0a uses two layers:
- **API Key + Secret** = identifies your app
- **Access Token + Secret** = identifies the user who authorized the app

### Troubleshooting (API)

| Error | Cause | Fix |
|---|---|---|
| 401 Unauthorized | Invalid/expired credentials | Regenerate tokens |
| 403 Forbidden | App lacks write permission | Enable Read+Write, regenerate tokens |
| 429 Rate limited | Over limit (~17 posts/day on free, more on paid) | Wait for reset |
| 503 Service Unavailable | X API down or paywall rejection | Retry, or check if plan is active |

---

## Option 2: Browser Automation (free)

Uses Playwright to drive a headless Chromium browser with your saved X session.

### Prerequisites

```bash
source venv/bin/activate
pip install playwright
playwright install chromium
```

### Setup

Extract cookies from your real browser where you're logged into X:

```bash
python x/files/setup_x_session.py
```

The script prompts for two cookies:
1. Open https://x.com in Chrome (logged in)
2. DevTools (`Cmd+Option+I`) → **Application** → **Cookies** → `https://x.com`
3. Copy `auth_token` (hex string) and `ct0` (longer alphanumeric string)

Session is saved to `~/.x_ansible/session.json`.

### Usage

```bash
ansible-playbook x/post_to_x_browser.yml -e 'post_text=hello from ansible'
```

### Debugging (visible browser)

```bash
ansible-playbook x/post_to_x_browser.yml -e 'post_text=test' -e 'headless=false'
```

### Module parameters (`x_post_browser`)

| Parameter | Required | Default | Description |
|---|---|---|---|
| `text` | Yes | — | Post text (1-280 characters) |
| `session_file` | No | `~/.x_ansible/session.json` | Path to saved session |
| `headless` | No | `true` | Run browser headlessly |
| `timeout` | No | `30` | Max seconds to wait for elements |

### Limitations

- **IP-locked:** Must run from the same network where your session cookies were created. Using from a different IP (e.g. a server) will likely trigger re-authentication.
- **TOS risk:** Browser automation violates X's Terms of Service. Low risk for personal low-volume use, but account suspension is possible.
- **Selector rot:** X changes their DOM periodically. If posting breaks, update the `data-testid` selectors in `library/x_post_browser.py`.
- **Bot detection:** X may detect automated browsers. If blocked, consider [Patchright](https://github.com/AliTriworlds/patchright) (drop-in Playwright replacement with anti-detection patches).
- **Session expiry:** Sessions last weeks to months. Re-run `setup_x_session.py` with fresh cookies when they expire.

### Troubleshooting (Browser)

| Error | Cause | Fix |
|---|---|---|
| Session expired | Cookies too old | Re-run `setup_x_session.py` with fresh cookies |
| Compose box not found | X changed selectors or session invalid | Check selectors, re-run setup |
| Post button disabled | Text not entered correctly | Try with `headless=false` to debug |
| Login redirect | Session invalid from this IP | Must run from same network as browser |
| playwright not found | Package not installed | `pip install playwright && playwright install chromium` |

---

## Notes

- Max post length on X is **280 characters**.
- Posting is non-idempotent: running twice = two posts.
- Both modules support `--check` mode.
- The `post_to_x_uri.yml` playbook is an alternative that shells out to Python inline — included for reference but the custom modules are preferred.
