# agent-harness-demo

A small agent harness in Python, built in five stages where each stage adds one thing to the one before. It's meant for teaching: put two neighbouring files side by side and the diff is the lesson.

The model sits behind a tiny interface. There's a Gemini adapter (google-genai) and a FakeModel that replays a script. The tests and the offline demos use the fake, so nothing here needs an API key unless you want to talk to a real model.

Every stage runs the same task: read the text files in `sandbox/` and write a summary report.

## Setup

Python 3.10 or newer.

    python -m venv .venv
    source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env

Get a key from https://aistudio.google.com/apikey and put it in `.env` as `GEMINI_API_KEY=...`. Exporting it in your shell works too.

The default model is `gemini-3.1-flash-lite`. Google renames and retires models fairly often, so if you get a "model not found" error, set `GEMINI_MODEL` in `.env` or pass `--model NAME`. Current names are at https://ai.google.dev/gemini-api/docs/models.

## Running

    python v0_model_only.py
    python v1_loop.py
    python v2_tools.py
    python v3_safety.py
    python v4_context.py

Add `--fake` to run any stage against the scripted FakeModel, with no key and no network. The fake's "summary" is canned text that matches the sample files, so it only shows the flow, not what a model would write.

The trace (every model turn, tool call and result) goes to stderr and the final answer to stdout. v2 to v4 write `report.md`, which is git-ignored.

Other flags:

- `--task "..."` changes the task
- `--yes` (v3, v4) approves writes and shell commands without asking
- `--sandbox DIR` and `--max-steps N` (v3, v4)
- `--max-chars N` (v4) sets the size at which the transcript gets trimmed

## Tests

    python -m pytest

The tests only use FakeModel. The real API is never called.

## Layout

    harness/model.py     message and tool types, Model interface, GeminiModel, FakeModel
    harness/trace.py     trace logger
    harness/cli.py       argument parsing, .env loading, picking the model
    harness/scripts.py   the scripted replies behind --fake
    v0_model_only.py ... v4_context.py
    sandbox/             three small text files
    tests/

The interface is one method, `generate(messages, tools, system) -> Message`, and the rest of the code only talks to that. GeminiModel converts to and from google-genai types. FakeModel returns the next message from its list and remembers what it was sent, which is what the tests inspect.

## The stages

### v0: model alone

One prompt, one answer, no tools. Ask it to read `sandbox/` and it can't. A good model says so; a weaker one may make up contents. Either way it shows that a model on its own only produces text.

### v1: the loop and one tool

Call the model. If it asks for a tool, run it, append the result, and call the model again. Stop when it replies with plain text. That loop is the agent.

Automatic function calling is turned off in the Gemini adapter, so the SDK doesn't run the loop for you and each step shows up in the trace. A single model message can contain several tool calls, and each one gets a result back in the next message.

Give it a path that doesn't exist and the whole run crashes with FileNotFoundError. v3 deals with that.

### v2: more tools

`read_file`, `write_file`, `list_dir` and `run_shell`. The loop is exactly the same as v1, only the tool list is longer. Nothing restricts where it can write or what it can run, and an exception in any tool still ends the run.

### v3: guardrails

Four changes:

- `write_file` and `run_shell` ask y/n before running. If you say no, the model gets "Error: permission denied by user" back as the tool result and can try something else.
- Every path is resolved against the sandbox folder (symlinks included) and rejected if it ends up outside it, so `../x` and `/etc/passwd` both fail.
- The loop is capped at `max_steps`. If the model never stops, the run ends with `stop="max_steps"`.
- Tool exceptions become `Error: ...` results that go back to the model, so it can retry or change approach.

Answer `n` at the write prompt to see a denial in the trace, or run with `--max-steps 2` to hit the limit.

### v4: trimming and a todo list

Long tasks fill up the context window, so before each model call `trim()` shortens what gets sent: it keeps the original task and the last couple of model/tool exchanges, blanks out older tool outputs, and if that isn't enough, drops the oldest exchanges. Exchanges are dropped whole so a tool call never loses its result, which the API would reject. The full history stays in memory; only the copy sent to the model is trimmed.

Trimming would also throw away the model's plan, so the plan is kept outside the transcript. The `update_todos` tool edits a list held by the harness, and that list is added to the system prompt on every turn.

To see trimming happen, run `python v4_context.py --fake --yes --max-chars 700` and look for `[trim]` lines.

## Notes and limits

- The Gemini adapter hasn't been run against the live API yet. It was only checked against a stub client for message conversion, tool declarations and the function-calling-off config. Treat the first real run as its first real test.
- Gemini 3 models want their "thought signatures" sent back with function calls. `Message.raw` keeps the provider's original response and the adapter replays it unchanged.
- `run_shell` uses the sandbox as its working directory and has a 10 second timeout, but a shell command can still `cd ..`. Only the permission prompt guards it, so don't treat it as real isolation. The path checks apply to the file tools.
- v1 and v2 use plain relative paths, which is why their task mentions `sandbox/...`. v3 and v4 treat the sandbox folder as the root.
- v1 and v2 use `while True` on purpose so the step limit in v3 is a visible change. v3 and v4 return a `Result(text, steps, stop)`.
- v4 counts characters, not tokens, to avoid another dependency. Tool output is cut at 10,000 characters in v3 and v4.
- v4 imports its tools and `execute` from v3 instead of copying them.
