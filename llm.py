import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import cast

import anthropic
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONObject
from pydantic import SecretStr


@dataclass
class FileResponse:
    fixes_needed: bool
    corrected_content: str
    summary: list[str]

class ModelTier(Enum):
    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes_needed": {
            "type": "boolean",
            "description": "Set to false if the text has no grammar or spelling errors. Set to true if fixes were made."
        },
        "corrected_content": {
            "type": "string",
            "description": "The fully corrected text. Only provide if fixes_needed is true."
        },
        "summary": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of changes made. Only provide if fixes_needed is true."
        }
    },
    "required": ["fixes_needed"]
}

def _user_message(filename: str, file_content: str) -> str:
    return f"=== {filename} ===\n{file_content}"

def call_claude(filename: str, file_content: str, system_prompt: str, model_tier: ModelTier, max_output_tokens: int) -> FileResponse:
    tools = [{
        "name": "submit_grammar_fixes",
        "description": "Submit the grammar fixes and summary",
        "input_schema": _TOOL_SCHEMA
    }]
    api_key = SecretStr(os.environ["LLM_API_KEY"])
    client = anthropic.Anthropic(api_key=api_key.get_secret_value())

    match model_tier:
        case ModelTier.CHEAP:
            model = "claude-haiku-4-5"
        case ModelTier.MEDIUM:
            model = "claude-sonnet-4-6"
        case ModelTier.EXPENSIVE:
            model = "claude-opus-4-7"

    response = client.messages.create(
        model=model,
        max_tokens=max_output_tokens,
        tools=tools,
        system=system_prompt,
        tool_choice={"type": "tool", "name": "submit_grammar_fixes"},
        messages=[{"role": "user", "content": _user_message(filename, file_content)}]
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Model output truncated for {filename!r}; file is too large for a single response. "
            f"Split the file or raise max_tokens."
        )

    result = response.content[0].input
    return FileResponse(
        fixes_needed=cast(bool, result.get("fixes_needed", False)),
        corrected_content=cast(str, result.get("corrected_content")),
        summary=cast(list[str], result.get("summary"))
    )

def call_deepseek(filename: str, file_content: str, system_prompt: str, model_tier: ModelTier, max_output_tokens: int) -> FileResponse:
    api_key = SecretStr(os.environ["LLM_API_KEY"])
    client = OpenAI(api_key=api_key.get_secret_value(), base_url="https://api.deepseek.com")

    _JSON_SCHEMA_PROMPT = (
        '\n\nRespond with a JSON object matching this schema exactly:\n'
        '{"fixes_needed": true/false, "corrected_content": "<corrected file content, optional>", "summary": ["<change 1>", ... optional]}'
    )

    match model_tier:
        case ModelTier.CHEAP:
            model = "deepseek-v4-flash"
        case ModelTier.MEDIUM:
            model = "deepseek-v4-flash"
        case ModelTier.EXPENSIVE:
            model = "deepseek-v4-pro"
    thinking_enabled = model_tier == ModelTier.EXPENSIVE
    user_content = _user_message(filename, file_content)
    if thinking_enabled:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_output_tokens,
            extra_body={"thinking": {"type": "enabled"}},
            response_format=ResponseFormatJSONObject(type="json_object"),
            messages=[
                ChatCompletionSystemMessageParam(role="system", content=system_prompt + _JSON_SCHEMA_PROMPT),
                ChatCompletionUserMessageParam(role="user", content=user_content),
            ],
        )
        if response.choices[0].finish_reason == "length":
            raise RuntimeError(
                f"Model output truncated for {filename!r}; file is too large for a single response. "
                f"Split the file or raise max_tokens."
            )
        result = json.loads(response.choices[0].message.content)
    else:
        tools: list[ChatCompletionToolParam] = [{
            "type": "function",
            "function": {
                "name": "submit_grammar_fixes",
                "description": "Submit the grammar fixes and summary",
                "parameters": _TOOL_SCHEMA
            }
        }]
        tool_choice: ChatCompletionNamedToolChoiceParam = {
            "type": "function",
            "function": {"name": "submit_grammar_fixes"}
        }
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_output_tokens,
            tools=tools,
            extra_body={"thinking": {"type": "disabled"}},
            tool_choice=tool_choice,
            messages=[
                ChatCompletionSystemMessageParam(role="system", content=system_prompt),
                ChatCompletionUserMessageParam(role="user", content=user_content),
            ],
        )
        if response.choices[0].finish_reason == "length":
            raise RuntimeError(
                f"Model output truncated for {filename!r}; file is too large for a single response. "
                f"Split the file or raise max_tokens."
            )
        result = json.loads(response.choices[0].message.tool_calls[0].function.arguments)

    return FileResponse(
        fixes_needed=cast(bool, result.get("fixes_needed", False)),
        corrected_content=cast(str | None, result.get("corrected_content")),
        summary=cast(list[str] | None, result.get("summary"))
    )
