"""Local development database seed script for Campus Quest.

Creates 6 clearly named sample checkpoints clustered around CAMPUS_CENTER
(offsets of roughly 40 to 150 metres, radius 30 metres).

STRICT SAFETY: Refuses to run if ENV=production.
"""

import sys
from typing import List, Tuple

import config
import db


SAMPLE_CHECKPOINTS: List[Tuple[str, float, float, float, int, str, str, str, str]] = [
    (
        "Central Library",
        22.69325,
        75.86760,
        30.0,
        1,
        "Seek the sanctuary of quiet minds and endless shelves of knowledge.",
        "Look near the grand stone steps facing the central avenue.",
        "Built in 1988, this library houses over 200,000 volumes across three floors.",
        "route",
    ),
    (
        "Administrative Block",
        22.69280,
        75.86828,
        30.0,
        2,
        "Where official stamps make decisions permanent and notices greet every visitor.",
        "Near the front porch pillars of the main administrative office.",
        "The administrative heart where every student registration begins.",
        "route",
    ),
    (
        "IMS Lawn",
        22.69230,
        75.86820,
        30.0,
        3,
        "Under the wide canopy where business minds unwind between case studies.",
        "Beside the shaded stone benches on the Institute of Management lawn.",
        "The iconic green lawn where student festivals and open discussions take shape.",
        "route",
    ),
    (
        "Takshashila Auditorium",
        22.69181,
        75.86760,
        30.0,
        4,
        "The grand stage of ovations, convocations, and university celebrations.",
        "Near the foyer entrance doors facing the central quadrangle.",
        "Seats 1,200 spectators and hosts the university's annual cultural conclaves.",
        "route",
    ),
    (
        "Sports Complex",
        22.69280,
        75.86633,
        30.0,
        5,
        "Where sweat meets teamwork and the echo of the referee's whistle sounds.",
        "By the perimeter fence overlooking the running track.",
        "Renovated in 2015, these grounds produced regional champions in athletics.",
        "route",
    ),
    (
        "University Main Gate",
        22.69370,
        75.86660,
        30.0,
        6,
        "The grand threshold through which every quest on this campus begins and ends.",
        "Beside the stone campus boundary plaque near the guardhouse.",
        "Thousands of students pass beneath this historic archway each morning.",
        "route",
    ),
]


def seed_database(db_path: str = None) -> int:
    """Populate sample checkpoints for local development and testing.

    Refuses execution when ENV is 'production'.
    Returns the number of checkpoints seeded.
    """
    if config.ENV == "production":
        print(
            "ERROR: seed.py is for local development only and cannot run in production.",
            file=sys.stderr,
        )
        raise RuntimeError("Refusing to seed database in production environment.")

    # Ensure tables exist
    db.init_db(db_path=db_path)

    conn = db.get_connection(db_path=db_path)
    try:
        with db.write_tx(conn):
            # Clean existing sample checkpoints for deterministic ordering in dev
            conn.execute("DELETE FROM checkpoints WHERE kind = 'route'")
            conn.executemany(
                """
                INSERT INTO checkpoints (
                    name, lat, lng, radius, position, clue, hint, story, kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                SAMPLE_CHECKPOINTS,
            )
        print(f"Successfully seeded {len(SAMPLE_CHECKPOINTS)} sample checkpoints.")
        return len(SAMPLE_CHECKPOINTS)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        seed_database()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
