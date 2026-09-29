# v2 => same loop as v1, only more tools (read, write, list, shell)
# nothing is restricted here and if a tool fails the whole run crashes. v3 fixes both

import subprocess
import sys
from pathlib import Path

from harness import cli, scripts
from harness.model import Message, Model, Tool, ToolResult
from harness.trace import Trace

SYSTEM = "You are an agent. Use the tools to complete the task. When finished, reply in plain text."
TASK = "Read every text file in sandbox/ and write a summary report to sandbox/report.md."


def read_file(path: str) -> str:
    return Path(path).read_text()


def write_file(path: str, content: str) -> str:
    Path(path).write_text(content)
    return f"wrote {len(content)} chars to {path}"


def list_dir(path: str = ".") -> str:
    return "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in Path(path).iterdir())) or "(empty)"


def run_shell(command: str) -> str:
    r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return f"exit {r.returncode}\n{r.stdout}{r.stderr}"


def _schema(*names):
    return {"type": "object", "properties": {n: {"type": "string"} for n in names}, "required": list(names)}


TOOLS = [
    Tool("read_file", "Read a UTF-8 text file.", _schema("path"), read_file),
    Tool("write_file", "Write text to a file, replacing it.", _schema("path", "content"), write_file),
    Tool("list_dir", "List a directory.", _schema("path"), list_dir),
    Tool("run_shell", "Run a shell command and return its output.", _schema("command"), run_shell),
]


def run_agent(task: str, model: Model, trace: Trace, tools: list[Tool] = TOOLS) -> str:
    by_name = {t.name: t for t in tools}
    messages = [Message("user", task)]
    while True:  # same loop as v1
        msg = model.generate(messages, tools, SYSTEM)
        messages.append(msg)
        trace.log("model", f"{msg.text!r} tool_calls={[c.name for c in msg.tool_calls]}")
        if not msg.tool_calls:
            return msg.text
        results = []
        for call in msg.tool_calls:
            trace.log("call", f"{call.name}({call.args})")
            output = by_name[call.name].fn(**call.args)
            trace.log("result", output)
            results.append(ToolResult(call.id, call.name, output))
        messages.append(Message("tool", tool_results=results))


def main(argv=None):
    args = cli.parse_args(TASK, argv)
    print(run_agent(args.task, cli.make_model(args, scripts.v2()), Trace()))


if __name__ == "__main__":
    sys.exit(main())
