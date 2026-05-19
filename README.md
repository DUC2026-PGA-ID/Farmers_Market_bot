# Farmers Market Bot

Telegram webhook bot for sharing farmers market information from Render.

## Features

- `/start` welcome message
- New user vs returning user tracking
- MySQL-backed Telegram user storage
- Admin user recognition
- Admin-only `/users` stats command
- Admin-only `/recentusers` command
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
ADMIN_USER_IDS=123456789,987654321
MYSQL_HOST=your-remote-mysql-host
MYSQL_PORT=3306
MYSQL_DATABASE=farmers_market_bot
MYSQL_USER=your-mysql-user
MYSQL_PASSWORD=your-mysql-password
WEBHOOK_URL=https://your-service.onrender.com
```

Notes:

- `BOT_TOKEN` must come from `@BotFather`
- `WEBHOOK_SECRET` can be any random string
- `ADMIN_USER_IDS` should be a comma-separated list of Telegram user IDs
- MySQL fields are optional if you want the bot to run without user storage
- For global Render deployment, `MYSQL_HOST` must be a remote/public MySQL server, not `127.0.0.1`
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

## User Management

When MySQL is configured, the bot will:

- save each Telegram user in a `users` table
- detect new users vs returning users
- keep the farmer fields `id`, `chat_id`, `first_name`, `gender`, and `joined_date`
- treat `chat_id` as the unique Telegram chat identifier
- mark admins from `ADMIN_USER_IDS` at runtime for admin-only commands

Current MySQL schema:

```sql
CREATE TABLE users (
    id BIGINT NOT NULL AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    gender VARCHAR(32) NOT NULL DEFAULT 'unknown',
    joined_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_chat_id (chat_id)
);
```

Notes:

- Telegram does not provide gender automatically, so the bot stores `unknown` by default until you add a separate gender collection flow
- `joined_date` is set when the farmer first starts the bot

Admin-only commands:

- `/users`: total farmers joined and how many joined today
- `/recentusers`: latest farmers saved in the `users` table

## Render Deploy

1. Push the repository to GitHub.
2. Create a new Render Blueprint from this repo.
3. Set `BOT_TOKEN` in Render Environment.
4. Set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` to your remote MySQL values if you want global user storage.
5. Deploy the latest commit.
6. Open `/setup-webhook` once if needed.
7. Test the bot in Telegram.

## Global Recommendation

For a fully global setup:

- keep the bot on Render
- use a remote MySQL database
- do not use local XAMPP MySQL with Render

Why:

- `127.0.0.1` on your laptop points to XAMPP on your laptop
- `127.0.0.1` on Render points to the Render container, not your laptop

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
