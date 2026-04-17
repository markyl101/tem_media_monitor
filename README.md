# TEM Media Monitor

Automated media monitoring pipeline for TEM Energy. Scans news, competitor blogs, Reddit, and regulatory sources hourly, scores items with Claude AI, and routes alerts to Slack with a weekly email newsletter.

## Architecture

```
Hourly cron (GitHub Actions)
    │
    ├── Web search (Google News RSS)
    ├── Competitor blogs (RSS feeds)
    ├── Reddit (r/energy via Apify)
    ├── Ofgem / Elexon / GOV.UK (regulatory feeds)
    │
    ▼
Deduplicate (seen_urls.json committed to repo)
    │
    ▼
Claude Haiku: score 1-10, classify, summarise
    │
    ├── Score 8-10 → Instant Slack alert (#tem-intel-alerts-test)
    ├── Score 4-7  → Daily digest queue (#tem-intel-digest-test)
    └── Score 1-3  → Log only
    │
    ▼
Weekly: Claude Sonnet generates narrative newsletter → Gmail
```

## GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for scoring and newsletter |
| `SLACK_BOT_TOKEN` | Yes | Slack bot token with `chat:write` scope |
| `GMAIL_ADDRESS` | Yes | Gmail address for newsletter sending |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app password ([create one here](https://myaccount.google.com/apppasswords)) |
| `NEWSLETTER_RECIPIENTS` | Yes | Comma-separated recipient email addresses |
| `APIFY_API_TOKEN` | No | Apify token for Reddit scraping |

## Setup

### Slack bot

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Add the `chat:write` OAuth scope
3. Install to your workspace
4. Copy the Bot User OAuth Token → set as `SLACK_BOT_TOKEN` secret
5. Invite the bot to `#tem-intel-alerts-test` and `#tem-intel-digest-test`

### Gmail app password

1. Enable 2-factor auth on the Gmail account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Mail"
4. Set as `GMAIL_APP_PASSWORD` secret

### Test manually

```bash
# Trigger a workflow manually
gh workflow run "Hourly Scan"

# Watch the run
gh run watch
```

Or trigger any workflow from the **Actions** tab in GitHub.

## Commands

```bash
python -m src.main scan        # Fetch → dedup → score → route
python -m src.main digest      # Post daily digest to Slack
python -m src.main newsletter  # Generate + email weekly newsletter
python -m src.main prune       # Clean URLs older than 30 days
```

## Schedules

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| Hourly Scan | Every hour | Full pipeline: fetch, score, alert |
| Daily Digest | 9am UTC, Mon–Fri | Posts grouped digest to Slack |
| Weekly Newsletter | Monday 9am UTC | Emails narrative briefing |
| Monthly Prune | 1st of month, 3am UTC | Cleans old URLs from state |

> Times are UTC. 9am UTC = 10am BST (summer) / 9am GMT (winter).

## Customisation

**Add keywords**: Edit `config.yml` → `keywords` section.

**Add RSS feeds**: Edit `config.yml` → `rss_feeds` section.

**Adjust scoring thresholds**: Edit `config.yml` → `scoring.instant_alert_min` and `scoring.digest_min`.

**Tune scoring logic**: Edit the system prompt in `src/scoring.py`.

**Switch models**: Edit `config.yml` → `scoring.model`. Newsletter always uses Sonnet for writing quality.
