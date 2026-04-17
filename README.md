# tem media monitor

Automated media monitoring pipeline for tem energy. Scans news, competitor blogs, Reddit, and regulatory sources hourly, scores items with Claude AI, and routes alerts to Slack with a weekly email newsletter.

## Architecture

```
Hourly cron (GitHub Actions)
    │
    ├── Web search (Google News RSS + optional NewsAPI)
    ├── Competitor blogs (RSS feeds)
    ├── Reddit (r/energy)
    ├── Ofgem / Elexon / GOV.UK (regulatory feeds)
    │
    ▼
Deduplicate (seen_urls.json in repo)
    │
    ▼
Claude Haiku: score 1-10, classify, summarise
    │
    ├── Score 8-10 → Instant Slack alert (#market-intel)
    ├── Score 4-7  → Daily digest queue (#service-content-and-credibility)
    └── Score 1-3  → Log only
    │
    ▼
Weekly: Claude Sonnet generates narrative newsletter → Gmail
```

## Setup

### 1. Create the repo

```bash
gh repo create tem-energy/media-monitor --private
cd media-monitor
# Copy all files from this project
git add -A && git commit -m "Initial commit" && git push
```

### 2. Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for scoring and newsletter |
| `SLACK_BOT_TOKEN` | Yes | Slack bot token with `chat:write` scope |
| `GMAIL_ADDRESS` | Yes | Gmail address for newsletter sending |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app password ([create one here](https://myaccount.google.com/apppasswords)) |
| `NEWSLETTER_RECIPIENTS` | Yes | Comma-separated email addresses |
| `NEWSAPI_KEY` | No | NewsAPI key for broader news coverage |
| `REDDIT_CLIENT_ID` | No | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | No | Reddit API client secret |

### 3. Create the Slack bot

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Add the `chat:write` OAuth scope
3. Install to your workspace
4. Copy the Bot User OAuth Token → set as `SLACK_BOT_TOKEN` secret
5. Invite the bot to `#market-intel` and `#service-content-and-credibility`

### 4. Gmail app password

1. Enable 2-factor auth on the Gmail account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Mail"
4. Set as `GMAIL_APP_PASSWORD` secret

### 5. Test it

```bash
# Trigger the scan manually
gh workflow run "Hourly Scan"

# Watch the run
gh run watch
```

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
| Daily Digest | 7am UTC weekdays | Posts grouped digest to Slack |
| Weekly Newsletter | Monday 8am UTC | Emails narrative briefing |
| Monthly Prune | 1st of month | Cleans old URLs from state |

## Customisation

**Add keywords**: Edit `config.yml` → `keywords` section.

**Add RSS feeds**: Edit `config.yml` → `rss_feeds` section.

**Adjust scoring**: Edit the system prompt in `src/scoring.py`. The scoring guide and category definitions live there.

**Change thresholds**: Edit `config.yml` → `scoring.instant_alert_min` and `scoring.digest_min`.

**Switch models**: Edit `config.yml` → `scoring.model`. Newsletter always uses Sonnet for writing quality.

## Costs

At hourly runs with ~50 new items/day:
- **Claude Haiku scoring**: ~$0.50/month
- **Claude Sonnet newsletter**: ~$0.20/month (weekly)
- **GitHub Actions**: Well within free tier (~30 min/day)
- **NewsAPI**: Free tier = 100 requests/day (plenty)
