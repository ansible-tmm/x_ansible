# Reddit Integration

Post to Reddit using Ansible and the Reddit Data API (OAuth2).

## Authentication

This module uses a **script-type OAuth app** (free, non-commercial personal use). You need:

| Variable | Description |
|----------|-------------|
| `REDDIT_CLIENT_ID` | OAuth app client ID (from reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | OAuth app client secret |
| `REDDIT_USERNAME` | Your Reddit username |
| `REDDIT_PASSWORD` | Your Reddit password |
| `REDDIT_SUBREDDIT` | Default subreddit to post to (e.g. `ansible` or `u_YourUsername`) |

## Setup

1. **Create a Reddit app** at https://www.reddit.com/prefs/apps
   - Type: **script**
   - Redirect URI: `http://localhost:8080` (not actually used for script apps)
   - Note the **client ID** (under the app name) and **secret**

2. **Export credentials**:
   ```bash
   export REDDIT_CLIENT_ID="your_client_id"
   export REDDIT_CLIENT_SECRET="your_client_secret"
   export REDDIT_USERNAME="your_username"
   export REDDIT_PASSWORD="your_password"
   export REDDIT_SUBREDDIT="u_your_username"
   ```

3. **Install Python dependency**:
   ```bash
   pip install requests
   ```

## Usage

### Post a link

```bash
ansible-playbook reddit/post_to_reddit.yml \
  -e title="Automating Meraki with Ansible" \
  -e url="https://blogs.cisco.com/developer/elevating-meraki-operations-ansible-automation" \
  -e subreddit="ansible"
```

### Post text to your profile

```bash
ansible-playbook reddit/post_to_reddit.yml \
  -e title="New automation project" \
  -e text="Just shipped a tool that generates social media posts with AI and publishes them via Ansible" \
  -e subreddit="u_IPvSean"
```

### Post with flair

```bash
ansible-playbook reddit/post_to_reddit.yml \
  -e title="My post" \
  -e url="https://example.com" \
  -e subreddit="ansible" \
  -e flair_id="abc123-flair-id"
```

## How It Works

1. The `reddit_post` Ansible module authenticates using OAuth2 password grant
2. Obtains a short-lived access token from Reddit
3. Submits the post via `POST https://oauth.reddit.com/api/submit`
4. Returns the post ID and URL on success

## Limitations

- Reddit API access requires manual approval for new applications (submitted, pending)
- Rate limits: ~100 requests per minute for authenticated users
- Title max: 300 characters
- Post body max: 40,000 characters
- A post is either a link post OR a text post (not both)

## Integration with Web UI

Once credentials are configured, Reddit will appear alongside X, LinkedIn, and Bluesky in the web UI for AI-powered post generation and publishing.
