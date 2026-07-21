# Web UI

A local Flask web app for generating and publishing social media posts across all platforms.

## Features

- Text input for describing post content + optional URL and tone
- AI generates platform-specific posts (LinkedIn, Bluesky, X, Reddit)
- Editable preview with character counters per platform
- Individual publish buttons per platform + "Publish All"
- Editable system prompts to control AI persona
- Activity log showing backend operations

## Running

```bash
cd x_ansible
source venv/bin/activate
python webapp/app.py
```

Then open http://127.0.0.1:5001

## How It Works

1. You describe what you want to post and optionally provide a URL
2. Click "Generate" — the app runs `webapp/generate_only.yml` which calls the AI 4 times (once per platform)
3. AI-generated posts appear in editable textareas with live character counters
4. Edit to your liking, then click "Publish" per platform or "Publish All"
5. Publishing shells out to the platform-specific Ansible playbooks

## Architecture

```
webapp/
├── app.py                  # Flask backend (routes, subprocess calls to ansible-playbook)
├── generate_only.yml       # Ansible playbook for AI generation (writes JSON output)
├── templates/
│   └── index.html          # Frontend (vanilla JS, no build step)
├── static/
│   └── style.css           # Dark theme styling
└── README.md
```

## Platform-Specific Notes

| Platform | Character Limit | URL Counting |
|----------|----------------|--------------|
| LinkedIn | 3,000 | Actual length |
| Bluesky | 300 | Any URL = 22 chars |
| X (Twitter) | 280 | Any URL = 23 chars (t.co) |
| Reddit | Title: 300, Body: 40,000 | Actual length |

## Requirements

- Flask (`pip install flask` or use the venv)
- All platform credentials configured via environment variables
- `MAAS` env var set for AI generation
