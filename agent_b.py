import json
import subprocess
import re

CONFIG_FILE = "config.json"

# ---------------- Load Config ----------------
def load_config():
    if not CONFIG_FILE:
        return {"Label": [], "EmailMap": {}, "Friends": [], "HighPriorityEmails": []}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

# ---------------- Save Config ----------------
def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print("\n✅ Updated config.json:")
    print(json.dumps(config, indent=2))

# ---------------- Clean Duplicates ----------------
def clean_duplicates(config):
    config["Label"] = list(dict.fromkeys(config.get("Label", [])))
    config["Friends"] = list(dict.fromkeys(config.get("Friends", [])))
    config["HighPriorityEmails"] = list(dict.fromkeys(config.get("HighPriorityEmails", [])))
    return config

# ---------------- Case-insensitive cleanup ----------------
def normalize_case(config):
    # Deduplicate labels case-insensitively
    labels = config.get("Label", [])
    seen = {}
    for label in labels:
        seen[label.lower()] = label  # keep last version
    config["Label"] = list(seen.values())

    # Deduplicate friends
    friends = config.get("Friends", [])
    seen = {}
    for friend in friends:
        seen[friend.lower()] = friend
    config["Friends"] = list(seen.values())

    # Deduplicate high priority emails
    hp = config.get("HighPriorityEmails", [])
    seen = {}
    for email in hp:
        seen[email.lower()] = email
    config["HighPriorityEmails"] = list(seen.values())

    # Normalize EmailMap
    emailmap = config.get("EmailMap", {})
    new_map = {}
    for k, v in emailmap.items():
        new_map[k.lower()] = v
    config["EmailMap"] = new_map

    return config

# ---------------- Parse Instruction using LLM ----------------
def parse_instruction(instruction, config):
    prompt = f"""
You are a JSON editing assistant. You will ALWAYS return ONLY valid JSON (no explanations, no markdown, no text).
The JSON must have exactly these four keys:
- "Label" (list of strings)
- "EmailMap" (object mapping emails to labels)
- "Friends" (list of emails)
- "HighPriorityEmails" (list of emails)

Instruction: "{instruction}"

Current Config:
{json.dumps(config, indent=2)}

Update Rules:
- If asked to add/remove a label, update "Label". Removing a label also removes any EmailMap entries pointing to it.
- If asked to add/remove an email mapping, update "EmailMap".
- If asked to add/remove a friend, update "Friends".
- If asked to add/remove a high priority email, update "HighPriorityEmails".
- Removals are case-insensitive.
- Never introduce duplicates.
- Return the FULL updated JSON object ONLY.
"""

    result = subprocess.run(
        ["ollama", "run", "mistral"],
        input=prompt,
        capture_output=True,
        text=True
    )

    raw_output = result.stdout.strip()

    # --- extract last JSON block ---
    match = re.findall(r"\{[\s\S]*\}", raw_output)
    if match:
        last_block = match[-1]
        try:
            return json.loads(last_block)
        except json.JSONDecodeError:
            pass

    print("⚠️ Model output parsing failed. Raw response:", raw_output)
    return config

# ---------------- Main Loop ----------------
def main():
    config = load_config()

    while True:
        instruction = input("\n📝 Enter your config update instruction (or 'exit'): ")
        if instruction.lower() in ["exit", "quit"]:
            break

        updated_config = parse_instruction(instruction, config)
        updated_config = clean_duplicates(updated_config)
        updated_config = normalize_case(updated_config)
        save_config(updated_config)
        config = updated_config

if __name__ == "__main__":
    main()
