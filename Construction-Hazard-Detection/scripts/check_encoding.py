
import base64

label = "武汉工程大学"
encoded = base64.urlsafe_b64encode(label.encode('utf-8')).decode('utf-8')
print(f"Label: {label}")
print(f"Encoded: {encoded}")

existing_key_label = "5q2m5rGJ5bel56iL5aSn5a2m"
decoded_existing = base64.urlsafe_b64decode(existing_key_label).decode('utf-8')
print(f"Existing Label in Redis: {decoded_existing}")

if encoded == existing_key_label:
    print("MATCH")
else:
    print("MISMATCH")
