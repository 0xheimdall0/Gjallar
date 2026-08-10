import base64
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

vapid = Vapid()
vapid.generate_keys()

private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
public_raw = vapid.public_key.public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint
)

print(f"SIGNAL_VAPID_PRIVATE_KEY={b64(private_raw)}")
print(f"SIGNAL_VAPID_PUBLIC_KEY={b64(public_raw)}")