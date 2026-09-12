"""Local launcher; credentials stay in the standard AWS profile chain."""

from pathlib import Path

from dotenv import load_dotenv
import uvicorn


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    uvicorn.run("main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
