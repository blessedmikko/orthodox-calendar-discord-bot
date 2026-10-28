"""Holy Trinity Orthodox daily calendar -> polished Discord webhook embeds."""
import argparse
import os
import re
import time
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

CALENDAR_URL = 'https://www.holytrinityorthodox.com/calendar/calendar.php'
PUBLIC_URL = 'https://www.holytrinityorthodox.com/htc/orthodox-calendar/'
COLOUR = 0x8C733B  # muted icon-gold
DESCRIPTION_LIMIT = 3500  # lower than Discord's 4096 for safety


def fetch_calendar(day: date) -> tuple[str, str]:
    params = {
        'month': day.month, 'today': day.day, 'year': day.year,
        'dt': 1, 'header': 1, 'lives': 3, 'trp': 1, 'scripture': 1,
    }
    r = requests.get(CALENDAR_URL, params=params, timeout=35, headers={
        'User-Agent': 'OrthodoxCalendarDiscordBot/2.0 (noncommercial calendar integration)'
    })
    r.raise_for_status()
    r.encoding = r.apparent_encoding or 'windows-1251'
    soup = BeautifulSoup(r.text, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    for tag in soup.find_all(['br', 'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'tr']):
        tag.insert_before('\n')
        if tag.name == 'br':
            tag.replace_with('\n')
    text = soup.get_text(' ', strip=False)
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', line).strip() for line in text.splitlines()]
    clean = '\n'.join(line for line in lines if line)
    if len(clean) < 100 or not re.search(r'scripture|readings', clean, re.I):
        raise ValueError('Calendar readings absent or response incomplete; refusing to post.')
    # Unlike the previous version, do not fail solely because troparia are absent on a particular day.
    return clean, r.url


def split_at_lines(text: str, limit: int = DESCRIPTION_LIMIT) -> list[str]:
    """Preserve all text; split on lines when possible without exceeding embed limits."""
    parts, current = [], ''
    for line in text.split('\n'):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ''
            cut = line.rfind(' ', 0, limit + 1)
            if cut < limit // 2:
                cut = limit
            parts.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        possible = current + '\n' + line if current else line
        if len(possible) > limit:
            parts.append(current)
            current = line
        else:
            current = possible
    if current:
        parts.append(current)
    return parts


def divide_sections(text: str) -> list[tuple[str, str]]:
    """Use source section headings; fallback preserves text if their spelling varies."""
    markers = [
        (re.compile(r'^the scripture readings\s*:?$', re.I), '📖 Scripture readings'),
        (re.compile(r'^scripture readings\s*:?$', re.I), '📖 Scripture readings'),
        (re.compile(r'^troparion(?:s)?(?: and kontakion(?:s)?)?\s*:?$', re.I), '🎼 Troparia & hymns'),
        (re.compile(r'^kontakion(?:s)?\s*:?$', re.I), '🎼 Kontakia'),
    ]
    sections = []
    title = '☦ Principal commemorations & calendar'
    lines = []
    for line in text.splitlines():
        match = next((label for regex, label in markers if regex.fullmatch(line.strip())), None)
        if match:
            if lines:
                sections.append((title, '\n'.join(lines)))
            title, lines = match, []
        else:
            lines.append(line)
    if lines:
        sections.append((title, '\n'.join(lines)))
    return sections


def build_payloads(day: date, text: str, source_url: str, role_id: str = '') -> list[dict]:
    if role_id and not re.fullmatch(r'\d{15,22}', role_id):
        raise ValueError('DISCORD_ROLE_ID must be a numeric Discord role ID.')
    embeds = []
    for heading, body in divide_sections(text):
        for i, part in enumerate(split_at_lines(body)):
            embeds.append({
                'title': heading if i == 0 else f'{heading} (continued)',
                'description': part,
                'color': COLOUR,
                'footer': {'text': 'Holy Trinity Orthodox Calendar · Old Style (Julian)'},
            })
    if not embeds:
        raise ValueError('No calendar content to post.')
    embeds[0]['author'] = {'name': f'Daily Orthodox Calendar · {day:%d %B %Y} (UTC)'}
    embeds[0]['url'] = source_url
    payloads = []
    for idx, embed in enumerate(embeds):
        content = f'<@&{role_id}>' if idx == 0 and role_id else ''
        payloads.append({
            'username': '☦ Orthodox Calendar',
            'content': content,
            'embeds': [embed],
            'allowed_mentions': {'parse': [], 'roles': [role_id] if content else []},
        })
    return payloads


def post_payloads(webhook: str, payloads: list[dict]) -> None:
    for idx, payload in enumerate(payloads, 1):
        for attempt in range(4):
            r = requests.post(webhook, params={'wait': 'true'}, json=payload, timeout=40)
            if r.status_code == 429 and attempt < 3:
                try:
                    wait = float(r.json().get('retry_after', 2))
                except (ValueError, TypeError):
                    wait = 2
                time.sleep(min(max(wait, 1), 30))
                continue
            r.raise_for_status()
            break
        print(f'Posted embed {idx}/{len(payloads)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='Gregorian date YYYY-MM-DD; default today UTC')
    parser.add_argument('--post', action='store_true', help='Send to Discord; default preview')
    args = parser.parse_args()
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    content, source = fetch_calendar(day)
    role_id = os.environ.get('DISCORD_ROLE_ID', '').strip()
    payloads = build_payloads(day, content, source, role_id)
    print(f'{day}: {len(content)} characters, {len(payloads)} embed(s).')
    if args.post:
        webhook = os.environ.get('DISCORD_WEBHOOK_URL', '')
        if not webhook.startswith('https://discord.com/api/webhooks/'):
            raise ValueError('Set the DISCORD_WEBHOOK_URL GitHub Actions secret.')
        post_payloads(webhook, payloads)
    else:
        print('PREVIEW ONLY — nothing posted, no role ping')
        for i, p in enumerate(payloads, 1):
            print(f"\n--- Embed {i}: {p['embeds'][0]['title']} ---\n{p['embeds'][0]['description']}")
        if role_id:
            print(f'Configured role mention: {role_id} (live posts only)')


if __name__ == '__main__':
    main()
