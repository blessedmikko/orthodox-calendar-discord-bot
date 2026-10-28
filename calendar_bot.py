"""Post Holy Trinity's Julian-calendar commemorations, hymns and readings to Discord."""
import argparse
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

CALENDAR_URL = 'https://www.holytrinityorthodox.com/calendar/calendar.php'
PUBLIC_URL = 'https://www.holytrinityorthodox.com/htc/orthodox-calendar/'
MAX_CHARS = 1900


def fetch_calendar(day: date) -> tuple[str, str]:
    params = {
        'month': day.month, 'today': day.day, 'year': day.year,
        'dt': 1, 'header': 1, 'lives': 1, 'trp': 1, 'scripture': 1,
    }
    response = requests.get(CALENDAR_URL, params=params, timeout=35, headers={
        'User-Agent': 'OrthodoxCalendarDiscordBot/1.0 (personal calendar integration)'
    })
    response.raise_for_status()
    # Holy Trinity documents windows-1251 for its PHP output.
    response.encoding = response.apparent_encoding if response.apparent_encoding else 'windows-1251'
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    # Preserve paragraph boundaries, including saints and hymn stanzas.
    for tag in soup.find_all(['br', 'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4']):
        tag.insert_before('\n')
        if tag.name == 'br':
            tag.replace_with('\n')
    text = soup.get_text(' ', strip=False)
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    clean = '\n'.join(lines)
    if len(clean) < 100 or not re.search(r'scripture|readings', clean, re.I):
        raise ValueError('Calendar data seems incomplete; refusing to post.')
    if not re.search(r'tropar', clean, re.I):
        raise ValueError('Hymn section missing; refusing to post incomplete calendar.')
    return clean, response.url


def chunks_for_discord(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split on line boundaries first, splitting long lines only if required."""
    chunks, current = [], ''
    for original_line in text.split('\n'):
        line = original_line
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ''
            split_at = line.rfind(' ', 0, limit + 1)
            if split_at < limit // 2:
                split_at = limit
            chunks.append(line[:split_at].rstrip())
            line = line[split_at:].lstrip()
        candidate = (current + '\n' + line) if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def post_parts(webhook: str, chunks: list[str]) -> None:
    # requests handles transient retry-after responses only when explicitly retried.
    for i, part in enumerate(chunks, 1):
        r = requests.post(webhook, params={'wait': 'true'}, json={
            'username': 'Orthodox Calendar',
            'content': part,
            'allowed_mentions': {'parse': []},
        }, timeout=40)
        r.raise_for_status()
        print(f'Posted message {i}/{len(chunks)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='Gregorian date YYYY-MM-DD (default: today UTC)')
    parser.add_argument('--post', action='store_true', help='Send to Discord; otherwise preview only')
    args = parser.parse_args()
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    content, source = fetch_calendar(day)
    heading = f'☦ **Orthodox Calendar — {day:%d %B %Y} (Gregorian / Old Style)**'
    footer = f'\nSource: {PUBLIC_URL}\nDaily record: {source}'
    parts = chunks_for_discord(f'{heading}\n\n{content}\n{footer}')
    print(f'Date: {day}; {len(content)} characters; {len(parts)} Discord posts.')
    if args.post:
        webhook = os.environ.get('DISCORD_WEBHOOK_URL')
        if not webhook or not webhook.startswith('https://discord.com/api/webhooks/'):
            raise ValueError('Set a valid DISCORD_WEBHOOK_URL repository secret.')
        post_parts(webhook, parts)
    else:
        print('\n--- PREVIEW ONLY; nothing posted ---\n')
        print('\n\n[Next Discord message]\n\n'.join(parts))


if __name__ == '__main__':
    main()
