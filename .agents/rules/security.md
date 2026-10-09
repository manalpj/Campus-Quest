---
trigger: always_on
---

# Security rules
- Every /api/gods route uses require_admin. Add a test when you add a route.
- Every player route that changes state checks the device cookie.
- Parameterised SQL only. No string-built SQL.
- Validate and limit every input with pydantic. Respect MAX_BODY_BYTES.
- Cookies: HttpOnly always, Secure when ENV=production, SameSite set deliberately.
- Never log passwords, tokens, cookies or full request bodies.
- Error messages must not reveal file paths, SQL or stack traces to clients.
- Rate limits use the real client IP (Railway sets FORWARDED_ALLOW_IPS).