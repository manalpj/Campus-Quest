"""Database seed script for Campus Quest.

Populates sample or demo checkpoints into SQLite.
Usage:
    python seed.py              # Seeds local development checkpoints
    python seed.py --demo       # Seeds real checkpoints from docs/CHECKPOINTS_DRAFT.md
    python seed.py --demo --force # Forces seeding in production (ENV=production)

STRICT SAFETY: Refuses to run if ENV=production unless --force is explicitly provided.
"""

import argparse
import sys
from typing import List, Tuple

import config
import db


# Sample checkpoints for quick local development/testing
SAMPLE_CHECKPOINTS: List[Tuple[str, float, float, float, int, str, str, str, str]] = [
    (
        "A-Block",
        22.682198036539997,
        75.88089897699963,
        30.0,
        1,
        "I speak in gears, bolts, and motion, where machines are born through engineering devotion.",
        "Look for the place where machines, engines, and gears are studied.",
        "The Mechanical Block, also known as A-Block, is one of the oldest blocks at IET-DAVV. Known for its calm and peaceful atmosphere, it holds a special place on campus, where history meets the everyday hustle of college life.",
        "route",
    ),
    (
        "B-Block",
        22.68177161266897,
        75.88057878014807,
        30.0,
        2,
        "I turn logic into code and ideas into digital creation, where programming meets innovation.",
        "Look for the place where students write programs, develop software, and solve problems using computers.",
        "B-Block is connected with the world of computing, where logic meets creativity. It represents the journey from writing the first lines of code to building solutions that can make a difference.",
        "route",
    ),
    (
        "D-Block",
        22.680625027473685,
        75.88090548960824,
        30.0,
        3,
        "I bring tiny components and invisible signals together, where circuits come alive and technology takes shape.",
        "Find the place where students explore electronic circuits, components, and communication systems.",
        "D-Block houses Electronic Department I, where students explore the fascinating world of electronics. Through circuits, components, and experiments, they discover how modern technology works.",
        "route",
    ),
    (
        "E-Block",
        22.68061884049809,
        75.88145198966777,
        30.0,
        4,
        "I bring technology, teamwork, and new ideas together, where learning meets service and ambition finds its spark.",
        "Look for the place that houses the second electronics department, the NSS office, and the E-Cell office.",
        "E-Block houses Electronic Department II, along with the NSS office and E-Cell office. It brings together technical learning, community service, and entrepreneurship, where students can explore ideas and turn them into meaningful action.",
        "route",
    ),
    (
        "F-Block",
        22.681204263003096,
        75.87883869851395,
        30.0,
        5,
        "I stand apart from the rest, one of the newest in the race, with a peaceful lake in front and calmness all around my place.",
        "Cross to the newer, quieter side of campus and look for the building with a lake right in front of it.",
        "F-Block is one of the newest additions to the campus, standing on the opposite side from the other blocks. With a lake in front and a peaceful atmosphere around it, this home of Information Technology offers a calm setting amid the busy rhythm of college life.",
        "route",
    ),
    (
        "Backstage",
        22.68059552508878,
        75.88000343006911,
        30.0,
        6,
        "I hide behind a place where voices shine bright, beside an open ground where sports bring life.",
        "Look behind M-Block, near the stage connected to the sports ground.",
        "Tucked behind M-Block, the Backstage sits beside a ground filled with the energy of sports and campus activities. While the stage offers a space for performances and events, the nearby ground brings students together through games, teamwork, and friendly competition.",
        "route",
    ),
]

# Real checkpoints from docs/CHECKPOINTS_DRAFT.md
# Update or paste final verified field coordinates here before seeding live events.
DEMO_CHECKPOINTS: List[Tuple[str, float, float, float, int, str, str, str, str]] = [
    (
        "A-Block",
        22.682198036539997,
        75.88089897699963,
        30.0,
        1,
        "I speak in gears, bolts, and motion, where machines are born through engineering devotion.",
        "Look for the place where machines, engines, and gears are studied.",
        "The Mechanical Block, also known as A-Block, is one of the oldest blocks at IET-DAVV. Known for its calm and peaceful atmosphere, it holds a special place on campus, where history meets the everyday hustle of college life.",
        "route",
    ),
    (
        "B-Block",
        22.68177161266897,
        75.88057878014807,
        30.0,
        2,
        "I turn logic into code and ideas into digital creation, where programming meets innovation.",
        "Look for the place where students write programs, develop software, and solve problems using computers.",
        "B-Block is connected with the world of computing, where logic meets creativity. It represents the journey from writing the first lines of code to building solutions that can make a difference.",
        "route",
    ),
    (
        "D-Block",
        22.680625027473685,
        75.88090548960824,
        30.0,
        3,
        "I bring tiny components and invisible signals together, where circuits come alive and technology takes shape.",
        "Find the place where students explore electronic circuits, components, and communication systems.",
        "D-Block houses Electronic Department I, where students explore the fascinating world of electronics. Through circuits, components, and experiments, they discover how modern technology works.",
        "route",
    ),
    (
        "E-Block",
        22.68061884049809,
        75.88145198966777,
        30.0,
        4,
        "I bring technology, teamwork, and new ideas together, where learning meets service and ambition finds its spark.",
        "Look for the place that houses the second electronics department, the NSS office, and the E-Cell office.",
        "E-Block houses Electronic Department II, along with the NSS office and E-Cell office. It brings together technical learning, community service, and entrepreneurship, where students can explore ideas and turn them into meaningful action.",
        "route",
    ),
    (
        "F-Block",
        22.681204263003096,
        75.87883869851395,
        30.0,
        5,
        "I stand apart from the rest, one of the newest in the race, with a peaceful lake in front and calmness all around my place.",
        "Cross to the newer, quieter side of campus and look for the building with a lake right in front of it.",
        "F-Block is one of the newest additions to the campus, standing on the opposite side from the other blocks. With a lake in front and a peaceful atmosphere around it, this home of Information Technology offers a calm setting amid the busy rhythm of college life.",
        "route",
    ),
    (
        "Backstage",
        22.68059552508878,
        75.88000343006911,
        30.0,
        6,
        "I hide behind a place where voices shine bright, beside an open ground where sports bring life.",
        "Look behind M-Block, near the stage connected to the sports ground.",
        "Tucked behind M-Block, the Backstage sits beside a ground filled with the energy of sports and campus activities. While the stage offers a space for performances and events, the nearby ground brings students together through games, teamwork, and friendly competition.",
        "route",
    ),
]


def seed_database(db_path: str = None, demo: bool = False, force: bool = False) -> int:
    """Populate checkpoints for local development, testing, or live demo.

    Refuses execution when ENV is 'production' unless force=True.
    Returns the number of checkpoints seeded.
    """
    if config.ENV == "production" and not force:
        msg = "Refusing to seed database in production without --force."
        print(f"ERROR: {msg}", file=sys.stderr)
        raise RuntimeError(msg)

    # Ensure tables exist
    db.init_db(db_path=db_path)

    checkpoints_to_seed = DEMO_CHECKPOINTS if demo else SAMPLE_CHECKPOINTS
    source_name = "demo (CHECKPOINTS_DRAFT.md)" if demo else "sample development"

    conn = db.get_connection(db_path=db_path)
    try:
        with db.write_tx(conn):
            # Clean existing sample/demo checkpoints for deterministic ordering
            conn.execute("DELETE FROM checkpoints WHERE kind = 'route'")
            conn.executemany(
                """
                INSERT INTO checkpoints (
                    name, lat, lng, radius, position, clue, hint, story, kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                checkpoints_to_seed,
            )
        print(f"Successfully seeded {len(checkpoints_to_seed)} {source_name} checkpoints.")
        return len(checkpoints_to_seed)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Campus Quest database with checkpoints."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed real checkpoints from docs/CHECKPOINTS_DRAFT.md.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if ENV=production.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Target database path (defaults to config.DB_PATH).",
    )

    args = parser.parse_args()

    try:
        seed_database(db_path=args.db_path, demo=args.demo, force=args.force)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
