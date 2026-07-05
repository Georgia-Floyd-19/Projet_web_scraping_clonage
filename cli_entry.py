"""Entry point for pip-installed `web-cloner` command."""
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()


def cli_main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from main import main
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
