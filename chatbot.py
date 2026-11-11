"""DEPRECATED — early throwaway prototype, superseded by jarvis.py.

This was the first Ollama-only CLI proof of concept. The real assistant is now
the Tkinter desktop app in jarvis.py (Claude API + tool use + voice + integrations).
Kept only for reference; not part of the app. Run `python3 jarvis.py` instead.
"""

import sys

import ollama  # The Ollama library for running AI locally

print("[deprecated] chatbot.py is an old prototype — run 'python3 jarvis.py' instead.")
if input("Run the legacy CLI anyway? [y/N] ").strip().lower() not in ("y", "yes"):
    sys.exit(0)

# This list stores the full conversation so the AI remembers what was said before
messages = []

print("=" * 40)
print("   Legacy AI Chatbot (deprecated)")
print("   Powered by Llama 3.2 (free & local)")
print("   Type 'quit' to exit")
print("=" * 40)
print()

while True:
    # Get input from the user
    user_input = input("You: ").strip()

    # Exit if user types quit
    if user_input.lower() in ("quit", "exit", "bye"):
        print("\nAI: Goodbye! Have a great day!")
        break

    # Skip empty input
    if not user_input:
        continue

    # Add the user's message to the conversation history
    messages.append({"role": "user", "content": user_input})

    # Send the conversation to Llama and get a response
    response = ollama.chat(
        model="llama3.2",   # The local AI model to use
        messages=messages   # The full conversation history
    )

    # Extract the text from the response
    reply = response["message"]["content"]

    # Add the reply to the conversation history
    messages.append({"role": "assistant", "content": reply})

    # Print the response
    print(f"\nAI: {reply}\n")
