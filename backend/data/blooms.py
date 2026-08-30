import datetime
import re

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from data.connection import db_cursor
from data.users import User

from psycopg2.errors import UniqueViolation


@dataclass
class Bloom:
    id: int
    sender: User
    content: str
    sent_timestamp: datetime.datetime
    rebloom_count: int = 0
    # Set only when this bloom reached a timeline by being rebloomed. The bloom
    # keeps its original sender and send time either way.
    rebloomed_by: Optional[str] = None
    rebloomed_timestamp: Optional[datetime.datetime] = None

    @property
    def timeline_timestamp(self) -> datetime.datetime:
        """When this bloom entered the timeline - the rebloom time for a rebloom."""
        return self.rebloomed_timestamp or self.sent_timestamp


# Must match the pattern the front end uses to turn hashtags into links,
# otherwise blooms link to tags they were never indexed under.
HASHTAG_PATTERN = re.compile(r"\B#(\w+)")


# The columns every bloom query selects, in the order _bloom_from_row expects.
BLOOM_COLUMNS = """blooms.id, users.username, blooms.content, blooms.send_timestamp,
              (SELECT COUNT(*) FROM reblooms AS counted WHERE counted.bloom_id = blooms.id)"""


def _bloom_from_row(row) -> Bloom:
    bloom_id, sender_username, content, timestamp, rebloom_count = row
    return Bloom(
        id=bloom_id,
        sender=sender_username,
        content=content,
        sent_timestamp=timestamp,
        rebloom_count=rebloom_count,
    )


def _rebloom_from_row(row) -> Bloom:
    bloom = _bloom_from_row(row[:5])
    bloom.rebloomed_by = row[5]
    bloom.rebloomed_timestamp = row[6]
    return bloom


def add_bloom(*, sender: User, content: str) -> Bloom:
    # dict.fromkeys de-duplicates but keeps the order tags appear in. The
    # hashtags table is UNIQUE(hashtag, bloom_id), so a bloom that uses the same
    # tag twice would otherwise fail to insert.
    hashtags = list(dict.fromkeys(HASHTAG_PATTERN.findall(content)))

    now = datetime.datetime.now(tz=datetime.UTC)
    bloom_id = int(now.timestamp() * 1000000)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO blooms (id, sender_id, content, send_timestamp) VALUES (%(bloom_id)s, %(sender_id)s, %(content)s, %(timestamp)s)",
            dict(
                bloom_id=bloom_id,
                sender_id=sender.id,
                content=content,
                timestamp=datetime.datetime.now(datetime.UTC),
            ),
        )
        for hashtag in hashtags:
            cur.execute(
                "INSERT INTO hashtags (hashtag, bloom_id) VALUES (%(hashtag)s, %(bloom_id)s)",
                dict(hashtag=hashtag, bloom_id=bloom_id),
            )


def add_rebloom(*, rebloomer: User, bloom_id: int) -> None:
    with db_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO reblooms (bloom_id, rebloomer_id, rebloom_timestamp) VALUES (%(bloom_id)s, %(rebloomer_id)s, %(timestamp)s)",
                dict(
                    bloom_id=bloom_id,
                    rebloomer_id=rebloomer.id,
                    timestamp=datetime.datetime.now(datetime.UTC),
                ),
            )
        except UniqueViolation:
            # Already rebloomed - treat as idempotent, the same way follow() does.
            pass


def get_reblooms_for_users(
    usernames: List[str], *, limit: Optional[int] = None
) -> List[Bloom]:
    """Blooms these users have rebloomed, tagged with who rebloomed them and when."""
    if not usernames:
        return []

    kwargs = {"usernames": list(usernames)}
    limit_clause = make_limit_clause(limit, kwargs)
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT
              {BLOOM_COLUMNS}, rebloomers.username, reblooms.rebloom_timestamp
            FROM
              reblooms
              INNER JOIN blooms ON blooms.id = reblooms.bloom_id
              INNER JOIN users ON users.id = blooms.sender_id
              INNER JOIN users AS rebloomers ON rebloomers.id = reblooms.rebloomer_id
            WHERE
              rebloomers.username = ANY(%(usernames)s)
            ORDER BY reblooms.rebloom_timestamp DESC
            {limit_clause}
            """,
            kwargs,
        )
        return [_rebloom_from_row(row) for row in cur.fetchall()]


def get_blooms_for_user(
    username: str, *, before: Optional[int] = None, limit: Optional[int] = None
) -> List[Bloom]:
    with db_cursor() as cur:
        kwargs = {
            "sender_username": username,
        }
        if before is not None:
            before_clause = "AND send_timestamp < %(before_limit)s"
            kwargs["before_limit"] = before
        else:
            before_clause = ""

        limit_clause = make_limit_clause(limit, kwargs)

        cur.execute(
            f"""SELECT
              {BLOOM_COLUMNS}
            FROM
              blooms INNER JOIN users ON users.id = blooms.sender_id
            WHERE
              username = %(sender_username)s
              {before_clause}
            ORDER BY send_timestamp DESC
            {limit_clause}
            """,
            kwargs,
        )
        return [_bloom_from_row(row) for row in cur.fetchall()]


def get_bloom(bloom_id: int) -> Optional[Bloom]:
    with db_cursor() as cur:
        cur.execute(
            f"SELECT {BLOOM_COLUMNS} FROM blooms INNER JOIN users ON users.id = blooms.sender_id WHERE blooms.id = %s",
            (bloom_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _bloom_from_row(row)


def get_blooms_with_hashtag(
    hashtag_without_leading_hash: str, *, limit: int = None
) -> List[Bloom]:
    kwargs = {
        "hashtag_without_leading_hash": hashtag_without_leading_hash,
    }
    limit_clause = make_limit_clause(limit, kwargs)
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT
              {BLOOM_COLUMNS}
            FROM
              blooms INNER JOIN hashtags ON blooms.id = hashtags.bloom_id INNER JOIN users ON blooms.sender_id = users.id
            WHERE
              hashtag = %(hashtag_without_leading_hash)s
            ORDER BY send_timestamp DESC
            {limit_clause}
            """,
            kwargs,
        )
        return [_bloom_from_row(row) for row in cur.fetchall()]


def make_limit_clause(limit: Optional[int], kwargs: Dict[Any, Any]) -> str:
    if limit is not None:
        limit_clause = "LIMIT %(limit)s"
        kwargs["limit"] = limit
    else:
        limit_clause = ""
    return limit_clause
