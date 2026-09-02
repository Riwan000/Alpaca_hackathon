"""Top-level entrypoint for database seeding — task P1-DB-15."""

from backend.db.seed import DEMO_POSITIONS, DEMO_SNAPSHOT, main, seed_demo_portfolio

__all__ = ["DEMO_POSITIONS", "DEMO_SNAPSHOT", "main", "seed_demo_portfolio"]

if __name__ == "__main__":
    main()
