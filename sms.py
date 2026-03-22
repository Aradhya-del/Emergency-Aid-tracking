from twilio.rest import Client

account_sid = "Account _sid"
auth_token = "YOUR_AUTH_TOKEN"

client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Test message from aid tracking app ✅",
    from_="+123....",      # Your Twilio number
    to="+1234567890"         # Verified number
)

print("Message SID:", message.sid)

