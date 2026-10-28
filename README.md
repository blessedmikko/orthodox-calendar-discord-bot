# Orthodox Calendar → Discord (10:00 UTC)

Daily Old Style Orthodox commemorations, hymns, and Scripture readings from Holy Trinity Russian Orthodox Church (Baltimore). Uses the parish's documented [PHP calendar integration](https://www.holytrinityorthodox.com/htc/orthodox-calendar/for-webmasters/5-integration-with-php/), with `lives=1`, `trp=1`, `scripture=1`, `dt=1`, and `header=1`.

## Setup

1. Create a new GitHub repository and upload **all files**, retaining the `.github/workflows/daily-calendar.yml` folder hierarchy. Keep the repository's default branch active.
2. In Discord, choose the target channel → **Edit Channel → Integrations → Webhooks** (or Server Settings → Integrations), create a webhook, and copy its URL. Keep this URL secret.
3. In GitHub, go to **Settings → Secrets and variables → Actions → New repository secret**. Name it exactly `DISCORD_WEBHOOK_URL` and paste the full Discord URL.
4. Open **Actions → Daily Orthodox Calendar → Run workflow**. Leave **send_to_discord** unchecked to preview in the action log. Once verified, run again with it checked for a live test. **A live test posts real messages.**
5. Thereafter GitHub schedules a post each day at **10:00 UTC**, or as soon afterward as the scheduler actually starts. In British Summer Time this is **11:00 UK time**.

## Behaviour

- Uses the current **UTC calendar date**, sent explicitly to the calendar API, so its US host's date does not affect the result.
- Requests **all listed saints**, the calendar header, **troparia** (and whatever additional hymn material the endpoint actually returns), and Scripture readings.
- Includes both calendars' date information as supplied by the source. The heading uses the Gregorian date only; the service includes its own Gregorian/Julian display.
- Preserves original wording but converts HTML to text. Long results are split into multiple messages under Discord's 2,000-character content limit.
- Refuses to post obviously incomplete records; fetch errors fail the workflow.
- Disables mentions to avoid accidental pings.

## Important caveats

The official PHP endpoint documents troparia but does not guarantee a separate kontakion on every day. The script cannot add hymns absent from the source. Long days may generate several Discord messages. A failed run after some messages have already been sent can cause partial posts. `concurrency` prevents simultaneous workflow runs, **not** duplicates from subsequent manual runs; do not manually send twice for the same date. Scheduled GitHub Actions are **not punctuality guaranteed**, and may occasionally be delayed or skipped. There is no external persistent store to support exactly-once delivery.

## Development

```sh
pip install -r requirements.txt
python -m unittest discover -s tests
python calendar_bot.py                  # local preview, no webhook needed
python calendar_bot.py --date 2026-10-28
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' python calendar_bot.py --post
```

Source: https://www.holytrinityorthodox.com/htc/orthodox-calendar/
