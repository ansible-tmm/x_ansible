# x_ansible

Post messages to social platforms from Ansible playbooks.

## Supported platforms

| Platform | Cost | Auth method | Token refresh | Docs |
|---|---|---|---|---|
| [Bluesky](bluesky/) | Free | App Password | Never | [bluesky/README.md](bluesky/README.md) |
| [LinkedIn](linkedin/) | Free | OAuth 2.0 | Every 60 days | [linkedin/README.md](linkedin/README.md) |
| [X (Twitter)](x/) | Paid / Free* | OAuth 1.0a / Cookies | Never / Weeks | [x/README.md](x/README.md) |
| [Reddit](reddit/) | Free | OAuth 2.0 (script) | Per-request | [reddit/README.md](reddit/README.md) |
| [AI Content Generation](ai/) | Free | Bearer token (MAAS) | Never | [ai/README.md](ai/README.md) |

*X official API requires a paid plan (~$200+/month). Browser automation is free but against TOS.

## Quick start

```bash
# Clone and setup
git clone <repo-url> && cd x_ansible
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Post to Bluesky (easiest)

```bash
export BLUESKY_HANDLE="yourname.bsky.social"
export BLUESKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
ansible-playbook bluesky/post_to_bluesky.yml -e 'post_text=hello from ansible'
```

### Post to LinkedIn

```bash
# First time only — opens browser for OAuth
export LINKEDIN_CLIENT_ID="your-client-id"
export LINKEDIN_CLIENT_SECRET="your-client-secret"
python linkedin/files/setup_linkedin_token.py

# Then post (no env vars needed — reads saved token)
ansible-playbook linkedin/post_to_linkedin.yml -e 'post_text=hello from ansible'
```

### Post to X (browser automation)

```bash
# First time only
playwright install chromium
python x/files/setup_x_session.py

# Then post
ansible-playbook x/post_to_x_browser.yml -e 'post_text=hello from ansible'
```

### Post to Reddit

```bash
export REDDIT_CLIENT_ID="your-client-id"
export REDDIT_CLIENT_SECRET="your-client-secret"
export REDDIT_USERNAME="your-username"
export REDDIT_PASSWORD="your-password"
ansible-playbook reddit/post_to_reddit.yml \
  -e 'title="My Post Title" url="https://example.com" subreddit="ansible"'
```

## Project structure

```
x_ansible/
├── ai/
│   ├── tasks/ask_ai.yml           # Reusable AI task (any OpenAI-compatible API)
│   ├── generate_post.yml          # Generate + preview + publish workflow
│   └── README.md
├── bluesky/
│   ├── library/bluesky_post.py
│   ├── vars/credentials_example.yml
│   ├── post_to_bluesky.yml
│   └── README.md
├── linkedin/
│   ├── library/linkedin_post.py
│   ├── files/setup_linkedin_token.py
│   ├── vars/credentials_example.yml
│   ├── post_to_linkedin.yml
│   └── README.md
├── x/
│   ├── library/x_post.py, x_post_browser.py
│   ├── files/setup_x_session.py
│   ├── vars/credentials_example.yml
│   ├── post_to_x.yml, post_to_x_browser.yml
│   └── README.md
├── reddit/
│   ├── library/reddit_post.py
│   ├── post_to_reddit.yml
│   └── README.md
├── webapp/
│   ├── app.py
│   ├── generate_only.yml
│   ├── templates/index.html
│   └── static/style.css
├── venv/                          (gitignored)
├── requirements.txt
├── ansible.cfg
└── .gitignore
```

## Requirements

- Python 3.9+
- macOS or Linux
- A virtual environment (included in setup)

All Python dependencies (Ansible, requests, requests-oauthlib, playwright) are
installed into the venv via `requirements.txt`.

## Usage pattern

Every playbook follows the same pattern:

```bash
source venv/bin/activate
ansible-playbook <platform>/post_to_<platform>.yml -e 'post_text=Your message here'
```

All playbooks support:
- `-e 'post_text=...'` — pass text as an extra variable
- `--check` — dry run (validates inputs without posting)
- `--ask-vault-pass` — decrypt Vault-encrypted credentials

## Credential management

Each platform supports credentials via (in priority order):
1. **Module parameters** — for Ansible Vault usage
2. **Environment variables** — for shell/CI usage
3. **Config files** — saved by setup scripts (LinkedIn, X browser)

Secrets are never stored in playbooks or committed to git.

## Idempotency

Posting is inherently **non-idempotent**. Every successful run creates a new
post. Running the same playbook twice produces two posts. Design your
automation accordingly (e.g., use external state or locks to prevent duplicates).

## Common tasks

### Generate AI posts for all platforms (preview)

```bash
export MAAS="your-maas-key"
ansible-playbook ai/generate_post.yml -e 'content="Just shipped a new feature"'
```

### Generate + publish to all platforms

```bash
ansible-playbook ai/generate_post.yml -e 'content="Just shipped a new feature" publish=true'
```

### Post to multiple platforms manually

```bash
ansible-playbook bluesky/post_to_bluesky.yml linkedin/post_to_linkedin.yml \
  -e 'post_text=hello from ansible'
```

### Set up a cron job (post daily)

```bash
crontab -e
# Add:
0 9 * * * cd /path/to/x_ansible && source venv/bin/activate && ansible-playbook bluesky/post_to_bluesky.yml -e 'post_text=Good morning'
```

## License

See [LICENSE](LICENSE).
