# v1 => the agent loop. call the model -> if it asks for a tool, run it and feed the result back -> repeat

import sys
from pathlib import Path

from harness import cli, scripts
from harness.model import Message, Model, Tool, ToolResult
from harness.trace import Trace

SYSTEM = "You are an agent. Use the tools to answer. When you have the answer, reply in plain text."
TASK = ("Read sandbox/standup_notes.txt, sandbox/bug_report.txt and sandbox/reading_list.txt, "
        "then write a short summary report.")


def read_file(path: str) -> str:
    return Path(path).read_text()


TOOLS = [Tool(
    name="read_file",
    description="Read a UTF-8 text file and return its contents.",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    fn=read_file,
)]


def run_agent(task: str, model: Model, trace: Trace, tools: list[Tool] = TOOLS) -> str:
    by_name = {t.name: t for t in tools}
    messages = [Message("user", task)]
    while True:  # keeps going till the model replies without asking for a tool
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
    print(run_agent(args.task, cli.make_model(args, scripts.v1()), Trace()))


if __name__ == "__main__":
    sys.exit(main())
