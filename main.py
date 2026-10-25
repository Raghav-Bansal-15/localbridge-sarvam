import os
from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv()

client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

response = client.chat.completions(
    messages=[
        {"role": "user", "content": "Hello! Introduce yourself briefly in one sentence."}
    ],
    model="sarvam-105b-conversations",
)

print(response.choices[0].message.content)
