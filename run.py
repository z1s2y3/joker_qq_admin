import asyncio

from app import run
from config import load_env_file


if __name__ == "__main__":
    load_env_file()
    asyncio.run(run())

