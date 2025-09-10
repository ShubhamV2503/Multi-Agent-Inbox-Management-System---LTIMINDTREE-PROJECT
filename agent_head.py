import subprocess

def run_agent_a():
    print("\n🤖 Running Agent A (Mail Processor)...\n")
    subprocess.run(["python", "agent_a.py"])

def run_agent_b():
    print("\n🤖 Running Agent B (Config Updater)...\n")
    subprocess.run(["python", "agent_b.py"])

def main():
    while True:
        command = input("\n📝 Enter system call (or 'exit' to quit): ").strip().lower()

        if command == "exit":
            print("👋 Exiting Head Agent...")
            break

        elif "agent a" in command:
            run_agent_a()

        elif "agent b" in command:
            run_agent_b()

        else:
            print("⚠️ Unknown command. Try: 'system call run agent a' or 'system call run agent b'.")

if __name__ == "__main__":
    main()
