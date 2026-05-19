# Farmers Market Bot

Telegram webhook bot for sharing farmers market information from Render.

## Features

- `/start` welcome message
- Khmer reply keyboard
- Rice price button
- Pepper price button
- Market update button
- Contact button
- Render-ready webhook deployment

## Project Files

- `app.py`: Flask app and Telegram webhook handler
- `render.yaml`: Render Blueprint config
- `requirements.txt`: Python dependencies
- `.env.example`: example environment variables

## Environment Variables

Create a local `.env` file from `.env.example`.

```env
BOT_TOKEN=your-telegram-bot-token
WEBHOOK_SECRET=any-random-secret-string
WEBHOOK_PATH=/telegram/webhook
AUTO_SET_WEBHOOK=true
WEBHOOK_URL=https://your-service.onrender.com
```

Notes:

- `BOT_TOKEN` must come from `@BotFather`
- `WEBHOOK_SECRET` can be any random string
- On Render, `RENDER_EXTERNAL_URL` is provided automatically, so `WEBHOOK_URL` is optional there

## Local Run

This project is now configured for webhook hosting first.

```powershell
pip install -r requirements.txt
python app.py
```

Useful local routes:

- `GET /`
- `GET /healthz`
- `GET /setup-webhook`

## Render Deploy

1. Push the repository to GitHub.
2. Create a new Render Blueprint from this repo.
3. Set `BOT_TOKEN` in Render Environment.
4. Deploy the latest commit.
5. Open `/setup-webhook` once if needed.
6. Test the bot in Telegram.

Health URL:

```text
https://your-service.onrender.com/healthz
```

Webhook setup helper:

```text
https://your-service.onrender.com/setup-webhook
```

## Security

- Never commit `.env`
- Never share your Telegram bot token
- If a token is exposed, revoke it in `@BotFather` and create a new one

## Current Behavior

- Render receives Telegram updates at `/telegram/webhook`
- Requests are validated with the Telegram secret token header
- The app hashes `WEBHOOK_SECRET` into a Telegram-safe secret token automatically
