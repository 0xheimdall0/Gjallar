"""Send one push directly, printing whatever the push service says."""

import json

from app.config import settings
from app.db import connect
from pywebpush import WebPushException, webpush

conn = connect()
sub = conn.execute("SELECT * FROM push_subscriptions LIMIT 1").fetchone()

if sub is None:
    raise SystemExit("No subscriptions in the database.")

print("endpoint:", sub["endpoint"][:70], "...")
print("subject :", settings.vapid_subject)

try:
    response = webpush(
        subscription_info={
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        },
        data=json.dumps(
            {"id": 0, "title": "Gjallar test", "body": "direct from the CLI",
             "severity": "critical", "source": "cli"}
        ),
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
        ttl=3600,
    )
    print("OK — HTTP", response.status_code)
    print(response.text[:400])
except WebPushException as exc:
    print("FAILED:", exc)
    if exc.response is not None:
        print("status:", exc.response.status_code)
        print("body  :", exc.response.text[:400])
