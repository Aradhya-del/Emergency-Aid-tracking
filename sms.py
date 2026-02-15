from twilio.rest import Client

account_sid = "AC600926e628bfb15031238b623b4e1ae7"
auth_token = "9313988d78359cb1a192572c53523b4f"

client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Test message from aid tracking app ✅",
    from_="+12294598732",      # Your Twilio number
    to="+918197437307"         # Verified number
)

print("Message SID:", message.sid)

