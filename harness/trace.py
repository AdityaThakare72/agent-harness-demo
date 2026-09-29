import sys


class Trace:
    def __init__(self, quiet: bool = False, width: int = 200):
        self.events: list[tuple[str, str]] = []
        self.quiet = quiet
        self.width = width

    def log(self, kind: str, text: str) -> None:
        self.events.append((kind, text))
        if not self.quiet:
            line = text.replace("\n", "\\n")
            if len(line) > self.width:
                line = line[: self.width] + "..."
            print(f"[{kind:<6}] {line}", file=sys.stderr)

    def kinds(self) -> list[str]:
        return [k for k, _ in self.events]
