# agent-harness-demo

A minimal agent harness in Python, built up in five runnable stages (v0 to v4). Each stage adds one idea, so the diff between two neighbouring files is the lesson. The core is model-agnostic; Gemini (google-genai) is one adapter, and a scripted FakeModel drives the tests and the offline demos.

Demo task for every stage: read the text files in `sandbox/` and write a summary report.

## Setup

Python 3.10+.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then put your key in .env: GEMINI_API_KEY=...

Get a key at https://aistudio.google.com/apikey. You can also export it in your shell instead of using `.env`: `export GEMINI_API_KEY=...`. The default model is `gemini-3.1-flash-lite`; override it with `GEMINI_MODEL=...` in `.env` or `--model NAME`. Model names change, so check https://ai.google.dev/gemini-api/docs/models if you get a "model not found" error.

## Run each stage

    python v0_model_only.py
    python v1_loop.py
    python v2_tools.py
    python v3_safety.py            # asks y/n before write_file and run_shell
    python v4_context.py

Add `--fake` to any stage to run it offline against the scripted FakeModel (no key, no network). Add `--yes` to v3/v4 to auto-approve writes. The trace goes to stderr, the final answer to stdout. v2 to v4 write `report.md` (in `sandbox/`), which is git-ignored.

Other flags: `--task "..."` to change the task, `--sandbox DIR` and `--max-steps N` (v3, v4), `--max-chars N` (v4).

## Tests

    python -m pytest

All tests use FakeModel only. The real API is never called.

## Layout

    harness/model.py    Message/Tool types, Model interface, GeminiModel, FakeModel
    harness/trace.py    Trace logger (prints and records every event)
    harness/cli.py      argument parsing, .env loading, model selection
    harness/scripts.py  scripted replies used by --fake
    v0_model_only.py ... v4_context.py
    sandbox/            three sample text files
    tests/

The `Model` interface is one method: `generate(messages, tools, system) -> Message`. Everything else in the harness talks only to that. `GeminiModel` translates to and from google-genai types; `FakeModel` replays a list of messages and records what it was sent.

## Teaching flow

### v0: the model alone

One prompt in, one answer out. No tools. Ask it to read `sandbox/` and it cannot: at best it says so, at worst it invents contents. The point: a model only produces text; it has no hands.

Notice: `tools=[]`, no loop.

### v1: the agent loop and one tool

The whole idea of an agent is a loop: call the model; if it asks for a tool, run it, append the result, call the model again; stop when it answers in plain text.

Notice: automatic function calling is switched off in `GeminiModel` (`AutomaticFunctionCallingConfig(disable=True)`), so the SDK does not run the loop for you and every step is visible in the trace. A model message can carry several tool calls; each gets a result in the same tool message.

Try: give it a nonexistent path. The run crashes with FileNotFoundError. That is the first thing v3 fixes.

### v2: more tools

`read_file`, `write_file`, `list_dir`, `run_shell`. The loop is unchanged; only the tool list grew. Adding capability is cheap, which is exactly why it is dangerous.

Notice: nothing stops the agent from writing anywhere or running any command, and any tool exception still kills the run.

### v3: guardrails

Four additions, all small:

- Permissions: tools marked `risky` (`write_file`, `run_shell`) ask y/n first. A denial is not an exception; the model receives "Error: permission denied by user" and can change course.
- Sandbox: every path is resolved against the sandbox folder, including symlinks, and rejected if it lands outside (`../x`, `/etc/passwd`).
- Step limit: the loop is `for step in range(max_steps)`. A model that never stops gets cut off with `stop="max_steps"`.
- Errors as results: any tool exception becomes an `Error: ...` tool result, so the model can retry or adapt.

Try: answer `n` to the write prompt and watch the trace. Run with `--max-steps 2` to hit the limit.

### v4: context trimming and a todo tool

Long tasks fill the context window. `trim()` shrinks what is sent to the model on each call: keep the task and the most recent model/tool pairs, blank out older tool outputs, then drop the oldest pairs if still over budget. Pairs are kept together so the history stays valid for the API. The full transcript is kept locally; only the copy sent to the model is trimmed.

Trimming would also erase the model's plan, so the plan lives outside the transcript: the `update_todos` tool edits a list held by the harness, and the current list is added to the system prompt on every turn. State that must survive belongs in the harness, not in the chat history.

Try: `python v4_context.py --fake --yes --max-chars 700` and look for `[trim]` lines in the trace.

## Choices made and limits

- Default model is `gemini-3.1-flash-lite` (chosen from Google's deprecation notes because `gemini-2.5-flash` is scheduled for shutdown). It is configurable.
- `GeminiModel` was written against the google-genai SDK and checked offline against a stub client (message conversion, function declarations, function-calling-disabled config). It has not been run against the live API.
- Gemini 3 models require "thought signatures" to be sent back with function calls. `Message.raw` keeps the provider's original response content and the adapter replays it unchanged.
- `run_shell` runs with the sandbox as its working directory and a 10 second timeout, but a shell can still `cd ..`. The sandbox check covers the file tools; the shell is guarded only by the permission prompt. Do not treat this as real isolation.
- v1 and v2 use plain relative paths from the current directory (hence `sandbox/...` in their tasks); v3 and v4 treat the sandbox folder as the root.
- v1 and v2 use `while True` on purpose so the step limit in v3 is a visible change. v3 and v4 return a `Result(text, steps, stop)`.
- v4 measures context in characters, not tokens, to stay dependency-free.
- Tool output is truncated to 10,000 characters in v3 and v4.
- `--fake` replies are scripted: the "summary" is canned text matching the sample files, not the output of a model.
- v4 imports the tools and `execute` from v3 rather than copying them.
