
"""Holy Trinity Orthodox Calendar -> Discord webhook.

Fetch commemorations, readings, and hymns in independent requests
so that hymns cannot accidentally be appended to Scripture readings.
"""

import argparse
import os
import re
import time
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

CALENDAR_URL = "https://www.holytrinityorthodox.com/calendar/calendar.php"
PUBLIC_URL = "https://www.holytrinityorthodox.com/htc/orthodox-calendar/"

COLOUR = 0x8C733B
DESCRIPTION_LIMIT = 3500


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for tag in soup.find_all(
        ["br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"]
    ):
        tag.insert_before("\n")
        if tag.name == "br":
            tag.replace_with("\n")

    lines = [
        re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        for line in soup.get_text(" ", strip=False).splitlines()
    ]

    return "\n".join(line for line in lines if line)


def calendar_request(
    day: date,
    *,
    dt=0,
    header=0,
    lives=0,
    trp=0,
    scripture=0,
) -> str:

    params = {
        "month": day.month,
        "today": day.day,
        "year": day.year,
        "dt": dt,
        "header": header,
        "lives": lives,
        "trp": trp,
        "scripture": scripture,
    }

    response = requests.get(
        CALENDAR_URL,
        params=params,
        timeout=35,
        headers={
            "User-Agent": "OrthodoxCalendarDiscordBot/3.0"
        },
    )

    response.raise_for_status()
    response.encoding = (
        response.apparent_encoding or "windows-1251"
    )

    return html_to_text(response.text)


def fetch_calendar(day: date) -> tuple[str, str, str]:
    """Make independent requests for the three sections."""

    commemorations = calendar_request(
        day,
        dt=1,
        header=1,
        lives=3,
    )

    readings = calendar_request(
        day,
        scripture=1,
    )

    hymns = calendar_request(
        day,
        trp=1,
    )

    if len(commemorations) < 20:
        raise ValueError(
            "Calendar commemorations incomplete; refusing to post."
        )

    if len(readings) < 10 or not re.search(
        r"\b(?:scripture|reading|gospel|epistle|"
        r"matthew|mark|luke|john|romans)\b",
        readings,
        re.I,
    ):
        raise ValueError(
            "Scripture readings missing; refusing to post."
        )

    return commemorations, readings, hymns


def split_at_lines(
    text: str,
    limit: int = DESCRIPTION_LIMIT,
) -> list[str]:

    parts = []
    current = ""

    for line in text.splitlines():

        while len(line) > limit:

            if current:
                parts.append(current)
                current = ""

            cut = line.rfind(" ", 0, limit + 1)

            if cut < limit // 2:
                cut = limit

            parts.append(line[:cut].rstrip())
            line = line[cut:].lstrip()

        candidate = (
            current + "\n" + line
            if current
            else line
        )

        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate

    if current:
        parts.append(current)

    return parts


HYMN_HEADING = re.compile(
    r"^(?:(?:the )?"
    r"(troparion|troparia|kontakion|kontakia)\b|"
    r"(?:tone\s+[\w-]+\s*[:.–-]\s*)"
    r"(troparion|troparia|kontakion|kontakia)\b)",
    re.I,
)


def separate_hymns(text: str) -> list[tuple[str, str]]:
    """Separate clearly identified troparia and kontakia."""

    if not text.strip():
        return []

    groups = []
    pending = []
    current_kind = None

    def flush():
        if pending and any(x.strip() for x in pending):
            groups.append(
                (
                    current_kind or "hymns",
                    "\n".join(pending).strip(),
                )
            )

    for raw in text.splitlines():

        match = HYMN_HEADING.match(raw.strip())

        if match:
            flush()

            found = (
                match.group(1) or match.group(2)
            ).lower()

            current_kind = (
                "kontakion"
                if found.startswith("kontak")
                else "troparion"
            )

            pending = [raw.strip()]

        else:
            pending.append(raw)

    flush()

    titles = {
        "troparion": "🎶 Troparion",
        "kontakion": "🕊️ Kontakion",
        "hymns": "🎼 Liturgical hymns",
    }

    return [
        (titles[kind], body)
        for kind, body in groups
    ]


def build_payloads(
    day: date,
    commemorations: str,
    readings: str,
    hymns: str,
    role_id: str = "",
) -> list[dict]:

    if role_id and not re.fullmatch(
        r"\d{15,22}", role_id
    ):
        raise ValueError(
            "DISCORD_ROLE_ID must be a numeric Discord role ID."
        )

    sections = [
        (
            "☦ Principal commemorations",
            commemorations,
        ),
        (
            "📖 Scripture readings",
            readings,
        ),
    ]

    sections.extend(separate_hymns(hymns))

    embeds = []

    for heading, body in sections:

        for i, part in enumerate(split_at_lines(body)):

            embeds.append(
                {
                    "title": (
                        heading
                        if i == 0
                        else heading + " (continued)"
                    ),
                    "description": part,
                    "color": COLOUR,
                    "footer": {
                        "text": (
                            "Holy Trinity Orthodox Calendar "
                            "· Old Style (Julian)"
                        )
                    },
                    "url": PUBLIC_URL,
                }
            )

    embeds[0]["author"] = {
        "name": (
            f"Daily Orthodox Calendar "
            f"· {day:%d %B %Y} (UTC)"
        )
    }

    payloads = []

    for idx, embed in enumerate(embeds):

        mention_role = idx == 0 and bool(role_id)

        payloads.append(
            {
                "username": "☦ Orthodox Calendar",
                "content": (
                    f"<@&{role_id}>"
                    if mention_role
                    else ""
                ),
                "embeds": [embed],
                "allowed_mentions": {
                    "parse": [],
                    "roles": (
                        [role_id]
                        if mention_role
                        else []
                    ),
                },
            }
        )

    return payloads


def post_payloads(
    webhook: str,
    payloads: list[dict],
) -> None:

    for idx, payload in enumerate(payloads, 1):

        for attempt in range(4):

            response = requests.post(
                webhook,
                params={"wait": "true"},
                json=payload,
                timeout=40,
            )

            if (
                response.status_code == 429
                and attempt < 3
            ):
                try:
                    delay = float(
                        response.json().get(
                            "retry_after", 2
                        )
                    )
                except (ValueError, TypeError):
                    delay = 2

                time.sleep(
                    min(max(delay, 1), 30)
                )
                continue

            response.raise_for_status()
            break

        print(
            f"Posted embed {idx}/{len(payloads)}"
        )


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        help=(
            "Gregorian date YYYY-MM-DD; "
            "default today UTC"
        ),
    )

    parser.add_argument(
        "--post",
        action="store_true",
        help=(
            "Send to Discord; "
            "default is preview only"
        ),
    )

    args = parser.parse_args()

    day = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(timezone.utc).date()
    )

    commemorations, readings, hymns = fetch_calendar(day)

    role_id = os.environ.get(
        "DISCORD_ROLE_ID", ""
    ).strip()

    payloads = build_payloads(
        day,
        commemorations,
        readings,
        hymns,
        role_id,
    )

    print(
        f"{day}: {len(payloads)} embed(s)."
    )

    if args.post:

        webhook = os.environ.get(
            "DISCORD_WEBHOOK_URL", ""
        )

        if not webhook.startswith(
            "https://discord.com/api/webhooks/"
        ):
            raise ValueError(
                "Set the DISCORD_WEBHOOK_URL "
                "GitHub Actions secret."
            )

        post_payloads(webhook, payloads)

    else:

        print(
            "PREVIEW ONLY — "
            "nothing posted, no role ping"
        )

        for i, payload in enumerate(
            payloads, 1
        ):
            emb = payload["embeds"][0]

            print(
                f"\n--- Embed {i}: "
                f"{emb['title']} ---\n"
                f"{emb['description']}"
            )


if __name__ == "__main__":
    main()
