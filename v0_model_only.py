"""v0: the model alone. One prompt in, one answer out. No tools, no loop."""
import sys

from harness import cli, scripts
from harness.model import Message, Model
from harness.trace import Trace

SYSTEM = "You are a helpful assistant."
TASK = "Read every text file in sandbox/ and write a short summary report."


def run(task: str, model: Model, trace: Trace) -> str:
    messages = [Message("user", task)]
    answer = model.generate(messages, tools=[], system=SYSTEM)
    trace.log("model", answer.text)
    return answer.text


def main(argv=None):
    args = cli.parse_args(TASK, argv)
    print(run(args.task, cli.make_model(args, scripts.v0()), Trace()))


if __name__ == "__main__":
    sys.exit(main())
