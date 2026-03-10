# x_ansible

Post messages to X (Twitter) from Ansible.

## Design

This project uses a **custom Ansible module** (`library/x_post.py`) that calls the
X API v2 `POST /2/tweets` endpoint with OAuth 1.0a user-context authentication.

**Why a custom module instead of a raw `uri` task?**

OAuth 1.0a requires HMAC-SHA1 signing of every request — the nonce, timestamp,
base string, and signature all need to be computed at call time. Ansible's `uri`
module has no built-in OAuth support, so you'd need to shell out to Python anyway
for the signing step. Wrapping that in a proper Ansible module gives you:

- Native `changed` / `failed` reporting.
- Structured return values (`post_id`, `post_text`, `response`).
- `no_log` protection for secrets.
- `--check` mode support.
- Clean error messages for auth failures, rate limits, and bad requests.

An alternative playbook (`post_to_x_uri.yml`) is included that uses
`ansible.builtin.command` to call Python inline. It works, but is less
maintainable — see [Alternative: uri-based approach](#alternative-uri-based-approach).

## File structure

```
x_ansible/
├── library/
│   └── x_post.py                  # Custom Ansible module
├── vars/
│   └── credentials_example.yml    # Vault template (copy & encrypt)
├── post_to_x.yml                  # Main playbook (recommended)
├── post_to_x_uri.yml              # Alternative playbook (uri-based)
├── requirements.txt               # Python dependencies
├── .gitignore
└── README.md
```

## Prerequisites

- Python 3.9+
- An X (Twitter) developer account with a Project and App

## Setup

### 1. Create and activate the virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This installs Ansible, `requests-oauthlib`, and all dependencies into an
isolated venv. The venv keeps everything self-contained — no conflicts with
your system Python.

**Every time you open a new terminal**, activate the venv before running
playbooks:

```bash
source venv/bin/activate
```

You'll know it's active when your prompt shows `(venv)`.

To deactivate when you're done:

```bash
deactivate
```

### 2. Create X API credentials

1. Go to https://developer.x.com/en/portal/dashboard.
2. Create a **Project** and an **App** inside it (Free tier is enough for posting).
3. In your App settings, set **User authentication settings**:
   - App permissions: **Read and Write**
   - Type of App: choose what fits (Web App for automation is fine)
4. Under **Keys and tokens**, generate:
   - **API Key** and **API Key Secret** (also called Consumer Key / Secret)
   - **Access Token** and **Access Token Secret**
     - These must be generated **after** you set Read+Write permissions.
     - If you generated them before enabling write, regenerate them.

### 3. Export environment variables

```bash
export X_API_KEY="your-api-key"
export X_API_SECRET="your-api-key-secret"
export X_ACCESS_TOKEN="your-access-token"
export X_ACCESS_TOKEN_SECRET="your-access-token-secret"
```

You can put these in a `.env` file (already in `.gitignore`) and source it:

```bash
source .env
```

### 4. (Optional) Use Ansible Vault instead

```bash
cp vars/credentials_example.yml vars/credentials.yml
# Edit vars/credentials.yml with your real keys
ansible-vault encrypt vars/credentials.yml
```

Then uncomment the `vars_files` and credential parameters in `post_to_x.yml`.

## Usage

Always activate the venv first:

```bash
source venv/bin/activate
```

### Basic

```bash
ansible-playbook post_to_x.yml -e 'post_text=hello from ansible'
```

### With Vault

```bash
ansible-playbook post_to_x.yml \
  -e 'post_text=hello from ansible' \
  --ask-vault-pass
```

### Check mode (dry run — does not post)

```bash
ansible-playbook post_to_x.yml \
  -e 'post_text=hello from ansible' \
  --check
```

### Expected output

```
TASK [Publish post to X] *****************************************************
changed: [localhost]

TASK [Show result] ************************************************************
ok: [localhost] => {
    "msg": {
        "changed": true,
        "post_id": "1234567890123456789",
        "post_text": "hello from ansible"
    }
}
```

## Testing safely

1. **Check mode first** — run with `--check` to validate credentials and input
   without actually posting.
2. **Use a test/alt account** — if you want to avoid posting to your main
   account during development, create a second X account and generate keys for
   that app instead.
3. **Verify post length** — the module validates length (max 280 chars) before
   calling the API.
4. **Delete test posts** — after confirming it works, delete any test posts
   from your timeline.

## Idempotency note

**Posting is inherently non-idempotent.** Every successful run creates a new
post on X. There is no built-in duplicate detection. If you run the playbook
twice with the same text, you get two posts. This is expected behavior and is
documented in the module. Design your automation accordingly (e.g., use a
lock file or external state to prevent duplicate runs).

## Environment variables reference

| Variable                | Description                          | Required |
|------------------------|--------------------------------------|----------|
| `X_API_KEY`            | API Key (Consumer Key)               | Yes      |
| `X_API_SECRET`         | API Key Secret (Consumer Secret)     | Yes      |
| `X_ACCESS_TOKEN`       | OAuth 1.0a Access Token              | Yes      |
| `X_ACCESS_TOKEN_SECRET`| OAuth 1.0a Access Token Secret       | Yes      |

## Common failures and troubleshooting

### HTTP 401 — Unauthorized

- **Cause:** Invalid or expired credentials.
- **Fix:** Regenerate your Access Token and Secret in the X Developer Portal.
  Make sure you're using the correct API Key pair for the same app.

### HTTP 403 — Forbidden

- **Cause:** Your app doesn't have write permission, or the access tokens
  were generated before write was enabled.
- **Fix:**
  1. In the Developer Portal, confirm your app has **Read and Write** permission.
  2. **Regenerate** Access Token and Access Token Secret after enabling write.

### HTTP 429 — Too Many Requests

- **Cause:** You've hit the rate limit (Free tier: 17 posts per 24 hours on
  the create tweet endpoint).
- **Fix:** Wait and retry. The API returns a `x-rate-limit-reset` header with
  the Unix timestamp when the limit resets.

### `requests-oauthlib` not found

- **Cause:** The venv isn't activated, or dependencies weren't installed.
- **Fix:**
  ```bash
  source venv/bin/activate
  pip install -r requirements.txt
  ```

### Post text too long

- **Cause:** Text exceeds 280 characters.
- **Fix:** Shorten your text. The module rejects it before calling the API.

### Empty post text

- **Cause:** You forgot `-e 'post_text=...'` or the variable is empty.
- **Fix:** Always pass post text via extra vars or define it in your playbook.

### OAuth signature mismatch / `oauth_problem=signature_invalid`

- **Cause:** Clock skew on your machine, or copy-paste errors in keys (extra
  spaces, missing characters).
- **Fix:** Verify your system clock is accurate. Re-copy your keys carefully.

## Alternative: uri-based approach

`post_to_x_uri.yml` is included as a second version. It avoids the custom
module by running Python inline via `ansible.builtin.command`.

**Drawbacks compared to the custom module:**

| Aspect                  | Custom module (`x_post`) | uri-based playbook         |
|------------------------|--------------------------|----------------------------|
| Ansible integration    | Native changed/failed    | Manual parsing             |
| Error messages         | Structured, specific     | Raw JSON dump              |
| Check mode             | Supported                | Not supported              |
| Secret protection      | `no_log` on params       | Env vars only              |
| Maintainability        | Single Python file       | Inline Python in YAML      |
| Dependency             | Same (requests-oauthlib) | Same                       |

The uri-based version still requires `requests-oauthlib` because OAuth 1.0a
HMAC-SHA1 signing cannot be done in pure Ansible YAML. A truly pure `uri`
approach would require reimplementing the OAuth signature algorithm in Jinja2
filters, which is fragile and not recommended.

## License

See [LICENSE](LICENSE).
