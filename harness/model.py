import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


@dataclass
class ToolCall:
    name: str
    args: dict
    id: str = ""


@dataclass
class ToolResult:
    call_id: str
    name: str
    output: str
    is_error: bool = False


@dataclass
class Message:
    role: str  # "user", "model" or "tool"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None  # the provider's original response, sent back as it is (gemini 3 needs its thought signatures back)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # json schema
    fn: Callable[..., str]
    risky: bool = False


def reply(text: str = "", *calls: tuple[str, dict]) -> Message:
    tool_calls = [ToolCall(name, args, f"call_{i}") for i, (name, args) in enumerate(calls)]
    return Message("model", text, tool_calls)


class Model(ABC):
    @abstractmethod
    def generate(self, messages: list[Message], tools: list[Tool], system: str = "") -> Message:
        # returns the next model message -> text, tool calls or both
        ...


class FakeModel(Model):
    def __init__(self, script: list[Message], repeat_last: bool = False):
        self.script = list(script)
        self.repeat_last = repeat_last
        self.seen: list[dict] = []

    def generate(self, messages, tools, system=""):
        self.seen.append({"messages": list(messages), "tools": [t.name for t in tools], "system": system})
        i = len(self.seen) - 1
        if i < len(self.script):
            return self.script[i]
        if self.repeat_last and self.script:
            return self.script[-1]
        raise RuntimeError("FakeModel script exhausted")


class GeminiModel(Model):
    def __init__(self, name: str | None = None, api_key: str | None = None):
        from google import genai

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in.")
        self.client = genai.Client(api_key=key)
        self.name = name or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL

    def generate(self, messages, tools, system=""):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system or None,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
                for t in tools
            ])] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self.client.models.generate_content(
            model=self.name, contents=[self._to_content(m, types) for m in messages], config=config
        )
        content = response.candidates[0].content
        parts = (content.parts if content else None) or []
        text = "".join(p.text for p in parts if p.text and not p.thought)
        calls = [ToolCall(p.function_call.name, dict(p.function_call.args or {}), p.function_call.id or "")
                 for p in parts if p.function_call]
        return Message("model", text, calls, raw=content)

    @staticmethod
    def _to_content(m: Message, types):
        if m.role == "user":
            return types.Content(role="user", parts=[types.Part(text=m.text)])
        if m.role == "model":
            if m.raw is not None:
                return m.raw
            parts = [types.Part(text=m.text)] if m.text else []
            parts += [types.Part(function_call=types.FunctionCall(name=c.name, args=c.args, id=c.id or None))
                      for c in m.tool_calls]
            return types.Content(role="model", parts=parts)
        parts = [
            types.Part(function_response=types.FunctionResponse(
                name=r.name, id=r.call_id or None,
                response={"error": r.output} if r.is_error else {"output": r.output}))
            for r in m.tool_results
        ]
        return types.Content(role="user", parts=parts)
