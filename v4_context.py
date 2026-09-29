# v4 => long tasks. trim the transcript we send to the model, and keep the todo list outside the transcript
# so the plan survives the trimming

import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable

from harness import cli, scripts
from harness.model import Message, Model, Tool, ToolCall
from harness.trace import Trace
from v3_safety import Result, ToolError, ask_user, execute, make_tools

SYSTEM = ("You are an agent working inside a sandbox folder; all paths are relative to it. "
          "Start by calling update_todos with a short plan, and keep it current as you work. "
          "If a tool returns an error, adapt. When finished, reply in plain text.")
TASK = "Read every text file in the sandbox and write a summary report to report.md."
STATUSES = ("pending", "in_progress", "done")
MARKS = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}


def render(plan: list[dict]) -> str:
    return "\n".join(f"{MARKS[t['status']]} {t['text']}" for t in plan)


def make_todo_tool(plan: list[dict]) -> Tool:
    def update_todos(todos: list) -> str:
        items = []
        for t in todos:
            if not isinstance(t, dict) or not t.get("text") or t.get("status") not in STATUSES:
                raise ToolError(f"each todo needs 'text' and a 'status' in {STATUSES}, got {t!r}")
            items.append({"text": t["text"], "status": t["status"]})
        plan[:] = items
        return render(plan)

    item = {"type": "object", "required": ["text", "status"],
            "properties": {"text": {"type": "string"}, "status": {"type": "string", "enum": list(STATUSES)}}}
    schema = {"type": "object", "properties": {"todos": {"type": "array", "items": item}}, "required": ["todos"]}
    return Tool("update_todos", "Replace the whole todo list. Statuses: pending, in_progress, done.", schema, update_todos)


def size(m: Message) -> int:
    return len(m.text) + sum(len(r.output) for r in m.tool_results) + sum(len(str(c.args)) for c in m.tool_calls)


def total(messages: list[Message]) -> int:
    return sum(size(m) for m in messages)


def shrink(m: Message) -> Message:
    if not m.tool_results:
        return m
    return replace(m, tool_results=[replace(r, output="[output trimmed]") for r in m.tool_results])


# keeps the task + the last few model/tool pairs. older tool outputs get blanked first, then the oldest pairs are dropped
# pairs stay together so every tool call still has its result (the api rejects the history otherwise)
# recent pairs are never dropped, even if they alone are over the budget
def trim(messages: list[Message], max_chars: int, keep_turns: int = 2) -> list[Message]:
    if total(messages) <= max_chars:
        return messages
    head, rest = messages[0], messages[1:]
    cut = max(len(rest) - 2 * keep_turns, 0)
    old, recent = [shrink(m) for m in rest[:cut]], rest[cut:]

    def build(dropped: int) -> list[Message]:
        note = f"{head.text}\n[{dropped} earlier messages trimmed]" if dropped else head.text
        return [replace(head, text=note), *old[dropped:], *recent]

    dropped = 0
    while dropped < len(old) and total(build(dropped)) > max_chars:
        dropped += 2
    return build(dropped)


def run_agent(task: str, model: Model, root: Path, approve: Callable[[ToolCall], bool], trace: Trace,
              max_steps: int = 20, max_chars: int = 8000) -> Result:
    plan: list[dict] = []
    tools = make_tools(root) + [make_todo_tool(plan)]
    by_name = {t.name: t for t in tools}
    messages = [Message("user", task)]
    for step in range(1, max_steps + 1):
        # todo list goes in the system prompt every turn -> trimming cant erase the plan
        system = SYSTEM + (f"\n\nCurrent todo list:\n{render(plan)}" if plan else "")
        sent = trim(messages, max_chars)  # only this copy is trimmed, messages keeps the full history
        if sent is not messages:
            trace.log("trim", f"{len(messages)} msgs/{total(messages)} chars -> {len(sent)} msgs/{total(sent)} chars")
        msg = model.generate(sent, tools, system)
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
    args = cli.parse_args(TASK, argv, safety=True, context=True)
    approve = (lambda call: True) if args.yes else ask_user
    model = cli.make_model(args, scripts.v4())
    print(run_agent(args.task, model, Path(args.sandbox), approve, Trace(), args.max_steps, args.max_chars).text)


if __name__ == "__main__":
    sys.exit(main())
