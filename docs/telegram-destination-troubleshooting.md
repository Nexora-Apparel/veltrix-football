# Telegram destination recovery

The daily prediction pipeline and Telegram transport are separate. A successful prediction run does not prove Telegram delivery. The Telegram destination must be a chat that the configured bot can access.

## Fix `chat not found`

1. Open Telegram and search for the exact bot username associated with `TELEGRAM_BOT_TOKEN` (the token is created by BotFather).
2. Open the bot's private chat and press **Start**, or send `/start`. A bot generally cannot initiate a private conversation before the user starts it.
3. If the report should go to a group, add the bot to that group and send a message in the group. If it should go to a channel, add the bot to the channel with permission to post.
4. Retrieve the destination's numeric chat ID from an update received by the bot. One safe method is to use Telegram's Bot API `getUpdates` with the bot token in a private browser session; inspect the returned update's `message.chat.id` (or `channel_post.chat.id` for a channel). Never paste the token into a public website, chat, issue, or source file. If webhook updates are configured, `getUpdates` may not return updates until the webhook is removed; avoid changing webhook settings unless you know another integration does not depend on it.
5. In the GitHub repository, open **Settings → Secrets and variables → Actions** and replace `TELEGRAM_CHAT_ID` with that exact chat ID. Keep `TELEGRAM_BOT_TOKEN` private. For a group, the ID is often negative; copy it exactly rather than guessing.
6. Open **Actions → Daily Fixture Predictions → Run workflow**, select branch `main`, leave the date blank to use today's Africa/Lagos date, and run it.
7. Open the run and inspect **Send daily report to Telegram**. A successful step should print `Telegram report delivered for YYYY-MM-DD.`. If it fails, read the Telegram API description without sharing the bot token.

## Common causes

- The private chat was never started with `/start`.
- The chat ID belongs to a different bot, user, group, or channel.
- The bot was removed from a group/channel or lacks permission to post.
- A username was entered where the numeric chat ID is expected.
- The destination secret was changed in a different repository or environment.

## Verification boundary

A passing prediction job and a generated report do not prove message delivery. Delivery is verified only when the Telegram send step returns success and the report appears in the intended chat. Prediction output remains experimental and must not be treated as validated betting advice.
