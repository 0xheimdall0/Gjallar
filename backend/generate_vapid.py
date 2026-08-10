from app.vapid import generate_vapid_pair

private_key, public_key = generate_vapid_pair()

print(f"SIGNAL_VAPID_PRIVATE_KEY={private_key}")
print(f"SIGNAL_VAPID_PUBLIC_KEY={public_key}")