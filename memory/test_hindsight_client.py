from hindsight_client import Hindsight

client = Hindsight(base_url="http://localhost:8888")

# Retain a memory
client.retain(bank_id="my-bank", content="Alice works at Google")

# Recall memories
results = client.recall(bank_id="my-bank", query="What does Alice do?")
for r in results:
    print(r.text)

# Reflect - generate response with disposition
answer = client.reflect(bank_id="my-bank", query="Tell me about Alice")
print(answer.text)

client.close()