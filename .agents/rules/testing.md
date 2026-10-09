---
trigger: always_on
---

# Testing rules
- pytest. Tests live in tests/. Use a temporary database per test, never data/quest.db.
- Write the test first for pure logic in game.py.
- For endpoints use FastAPI TestClient.
- Every bug fix gets a test that fails before the fix.
- Run the whole suite before suggesting a commit message.