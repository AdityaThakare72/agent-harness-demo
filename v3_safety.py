# v3 => guardrails. permission prompt before write/shell, files stay inside the sandbox folder, a max steps limit
# and tool errors go back to the model as results so it can recover instead of the run crashing

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from harness import cli, scripts
from harness.model import Message, Model, Tool, ToolCall, ToolResult
from harness.trace import Trace

SYSTEM = ("You are an agent working inside a sandbox folder; all paths are relative to it. "
          "Use the tools to complete the task. If a tool returns an error, adapt. When finished, reply in plain text.")
TASK = "Read every text file in the sandbox and write a summary report to report.md."
MAX_OUTPUT = 10_000


class ToolError(Exception):
    pass


@dataclass
class Result:
    text: str
    steps: int
    stop: str  # "done" or "max_steps"


def make_tools(root: Path) -> list[Tool]:
    root = root.resolve()

    def safe(path: str) -> Path:
        p = (root / path).resolve()  # resolve() also follows symlinks, so a link pointing outside gets caught too
        if not p.is_relative_to(root):
            raise ToolError(f"path '{path}' is outside the sandbox")
        return p

    def read_file(path: str) -> str:
        return safe(path).read_text()

    def write_file(path: str, content: str) -> str:
        p = safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def list_dir(path: str = ".") -> str:
        return "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in safe(path).iterdir())) or "(empty)"

    def run_shell(command: str) -> str:
        r = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=10)
        return f"exit {r.returncode}\n{r.stdout}{r.stderr}"

    def schema(*names):
        return {"type": "object", "properties": {n: {"type": "string"} for n in names}, "required": list(names)}

    return [
        Tool("read_file", "Read a UTF-8 text file.", schema("path"), read_file),
        Tool("write_file", "Write text to a file, replacing it.", schema("path", "content"), write_file, risky=True),
        Tool("list_dir", "List a directory.", schema("path"), list_dir),
        Tool("run_shell", "Run a shell command in the sandbox folder.", schema("command"), run_shell, risky=True),
    ]


def ask_user(call: ToolCall) -> bool:
    return input(f"Allow {call.name}({call.args})? [y/N] ").strip().lower() == "y"


def execute(call: ToolCall, by_name: dict[str, Tool], approve: Callable[[ToolCall], bool], trace: Trace) -> ToolResult:
    def fail(msg: str) -> ToolResult:
        return ToolResult(call.id, call.name, f"Error: {msg}", is_error=True)

    tool = by_name.get(call.name)
    if tool is None:
        return fail(f"unknown tool '{call.name}'")
    if tool.risky and not approve(call):
        trace.log("denied", f"{call.name}({call.args})")  # not an exception, the model just gets told and can try something else
        return fail("permission denied by user")
    try:
        output = tool.fn(**call.args)
    except Exception as e:
        return fail(f"{type(e).__name__}: {e}")
    return ToolResult(call.id, call.name, output[:MAX_OUTPUT])


def run_agent(task: str, model: Model, root: Path, approve: Callable[[ToolCall], bool], trace: Trace,
              max_steps: int = 15) -> Result:
    tools = make_tools(root)
    by_name = {t.name: t for t in tools}
    messages = [Message("user", task)]
    for step in range(1, max_steps + 1):  # step limit so a looping model cant run forever
        msg = model.generate(messages, tools, SYSTEM)
        messages.append(msg)
        trace.log("model", f"step {step}: {msg.text!r} tool_calls={[c.name for c in msg.tool_calls]}")
        if not msg.tool_calls:
            return Result(msg.text, step, "done")
        results = []
        for call in msg.tool_calls:
            trace.log("call", f"{call.name}({call.args})")
            result = execute(call, by_name, approve, trace)
            trace.log("error" if result.is_error else "result", result.output)
            results.append(result)
        messages.append(Message("tool", tool_results=results))
    trace.log("stop", f"reached max_steps={max_steps}")
    return Result(f"Stopped: reached max_steps={max_steps} without a final answer.", max_steps, "max_steps")


def main(argv=None):
    args = cli.parse_args(TASK, argv, safety=True)
    approve = (lambda call: True) if args.yes else ask_user
    model = cli.make_model(args, scripts.v3())
    print(run_agent(args.task, model, Path(args.sandbox), approve, Trace(), args.max_steps).text)


if __name__ == "__main__":
    sys.exit(main())
