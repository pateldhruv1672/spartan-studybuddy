import asyncio
import os

os.environ["STUDYBUDDY_BROWSER_PROVIDER"] = "ollama"
os.environ["STUDYBUDDY_OLLAMA_MODEL"] = "qwen2.5:3b"
os.environ["STUDYBUDDY_BROWSER_MAX_STEPS"] = "4"
os.environ["STUDYBUDDY_OLLAMA_NUM_CTX"] = "8192"
os.environ["STUDYBUDDY_OLLAMA_URL"] = "http://127.0.0.1:11434"
os.environ["STUDYBUDDY_CDP_URL"] = "http://127.0.0.1:9222"

from mac_bridge import run_browser_use

async def main():
    task = (
        "The page is https://en.wikipedia.org/wiki/Message_queue. "
        "Navigate to the page ONE time only. After the page loads and you have "
        "read the first paragraph, your very next action must be `done` — do not "
        "navigate again for any reason. Your done answer must be a 2-3 sentence "
        "explanation of what a message queue actually IS (not a description of what "
        "the paragraph discusses), followed by the source URL on a new line. Example "
        "of the correct format: 'A message queue is [explanation]. It allows "
        "[explanation]. Source: [URL]'"
    )
    result = await run_browser_use(task)
    print("\n--- RESULT ---")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())