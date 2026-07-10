# FB Planner Audit

A Flask-based Messenger bot that audits Facebook ad creatives and copy against policy guidelines. Uses SQLite for storage, risky-word scanning with quota management, and scheduled policy updates.

## Features

- **Text Precheck**: Scan Messenger messages for risky words in Mongolian and English
- **Policy Updater**: Weekly fetch from `frc.mn` and `transparency.meta.com`
- **Quota Management**: Free tier (5 scans) + PRO subscriptions
- **QPay Integration**: Fake invoice stub for payment flow
- **Scheduled Audits**: Background job runs every 10 minutes
- **Rate Limiting**: Per-user spam protection

## Project Structure

```
fb-planner-audit/
├── bot/
│   ├── app.py              # Flask app, webhook, scheduler
│   ├── handlers.py         # Message/postback routing
│   └── templates.py        # Messenger templates
├── core/
│   ├── config.py           # YAML config loader
│   ├── models.py           # Pydantic models
│   ├── db.py               # SQLite database layer
│   ├── precheck.py         # Risky-word scanning + quota
│   ├── audit.py            # Audit logic + plan generation
│   ├── policy_updater.py   # Weekly policy extraction
│   └── qpay.py             # Payment/invoice stubs
├── data/
│   ├── app.db.example      # Example DB schema
│   └── risky_words.json    # Risky word dictionary
├── config.yaml             # Application config
├── render.yaml             # Render.com deployment
├── Dockerfile              # Production container
├── run.py                  # Entrypoint
├── test_v2.py              # pytest tests
└── requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml`:

```yaml
app:
  name: fb-planner-audit
  env: dev

fb:
  verify_token: fbplanneraudit_verify
  app_secret: ""
  page_id: ""
  page_token: ""
  webhook_url: ""

admin:
  telegram_user_id: 0
  telegram_bot_token: ""

scheduler:
  interval_minutes: 10

storage:
  db_path: data/app.db
```

## Running

```bash
# Webhook mode (default)
python run.py

# Or with environment variables
PORT=10000 RUN_MODE=webhook python run.py
```

## Testing

```bash
pytest test_v2.py -v
```

## Deployment

### Docker

```bash
docker build -t fb-planner-audit .
docker run -p 10000:10000 fb-planner-audit
```

### Render.com

1. Push to GitHub
2. Connect repo in Render dashboard
3. Set env vars: `META_TOKEN`, `QPAY_KEY`
4. Deploy

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `5000` |
| `RUN_MODE` | `webhook` or `polling` | `webhook` |
| `DEBUG` | Enable debug mode | `false` |
| `META_TOKEN` | Facebook page token | - |
| `QPAY_KEY` | Payment integration key | - |

## Security Notes

- SQLite queries use parameterized statements
- Rate limiting: 10 requests/minute per user
- Webhook verification via `hub.verify_token`
- `data/app.db` is gitignored

## License

Proprietary. All rights reserved.
