import argparse
import os
from pathlib import Path

from harness.model import FakeModel, GeminiModel


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def parse_args(default_task: str, argv=None, safety: bool = False, context: bool = False):
    p = argparse.ArgumentParser()
    p.add_argument("task", nargs="?", default=default_task)
    p.add_argument("--fake", action="store_true", help="use the scripted FakeModel (no API key needed)")
    p.add_argument("--model", default=None, help="Gemini model name (default: $GEMINI_MODEL or built-in)")
    if safety:
        p.add_argument("--yes", action="store_true", help="auto-approve write_file and run_shell")
        p.add_argument("--sandbox", default="sandbox", help="folder the agent is confined to")
        p.add_argument("--max-steps", type=int, default=15)
    if context:
        p.add_argument("--max-chars", type=int, default=8000, help="trim the transcript above this size")
    return p.parse_args(argv)


def make_model(args, script):
    if args.fake:
        return FakeModel(script)
    load_env()
    return GeminiModel(args.model)
