import os
import subprocess

from llm import call_claude, call_deepseek, ModelTier, FileResponse

system_prompt = """
You are a grammar and spelling checker for prose documents.

You will receive the full content of a single file, prefixed with === filename ===.
Your job is to:
- Fix grammar and spelling errors in prose only
- Never modify markup, commands, code, math, citations, or references (e.g. LaTeX commands and environments, Markdown syntax, code blocks, inline code)
- Never change the meaning or style of the writing, only correct clear errors
- Return corrected_content as the fully corrected file content
- Return a concise bullet list of what you changed in this file

If there are no grammar or spelling errors, return the original content unchanged and an empty summary list.
"""

append_prompt = os.environ.get("SYSTEM_PROMPT_APPEND", "").strip()
if append_prompt:
    system_prompt = system_prompt.rstrip() + "\n\n" + append_prompt


def parse_globs() -> list[str]:
    raw = os.environ["FILE_EXTENSIONS"]
    globs = [f"*.{ext.strip().lstrip('.')}" for ext in raw.split(",") if ext.strip().lstrip(".")]
    if not globs:
        raise ValueError(f"FILE_EXTENSIONS must list at least one extension, got: {raw!r}")
    return globs


def get_changed_files() -> dict[str, str]:
    before = os.environ["BEFORE_SHA"]
    after = os.environ["AFTER_SHA"]
    globs = parse_globs()
    changed = subprocess.run(
        args=["git", "diff", before, after, "--name-only", "--diff-filter=ACM", "--", *globs],
        capture_output=True,
        text=True
    ).stdout.strip()

    if not changed:
        return {}

    files = {}
    for path in changed.splitlines():
        with open(path) as f:
            files[path] = f.read()
    return files

def write_summary(message: str) -> None:
    print(message)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(f"### Grammar check\n\n{message}\n")


def check_file(provider: str, filename: str, body: str, model_tier: ModelTier, max_output_tokens: int) -> FileResponse:
    if provider == "deepseek":
        return call_deepseek(filename, body, system_prompt, model_tier, max_output_tokens)
    if provider == "claude":
        return call_claude(filename, body, system_prompt, model_tier, max_output_tokens)
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")


def main():
    provider = os.environ["LLM_PROVIDER"]
    model_tier = ModelTier(os.environ.get("LLM_TIER", "").strip().lower() or "medium")
    max_output_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "16384"))
    files = get_changed_files()

    if not files:
        write_summary("No matching files changed — nothing to check.")
        return

    corrected_files: dict[str, str] = {}
    summary: list[str] = []
    for filename, body in files.items():
        result = check_file(provider, filename, body, model_tier, max_output_tokens)
        if not result.fixes_needed:
            continue
        corrected_files[filename] = result.corrected_content
        summary.extend(f"`{filename}`: {point}" for point in result.summary)

    if not summary:
        write_summary(f"Checked {len(files)} file(s), no grammar issues found.")
        return

    for filename, content in corrected_files.items():
        with open(filename, "w") as file:
            file.write(content)

    with open("pr_description.md", "w") as file:
        file.write("## Grammar Fixes\n\n")
        file.write("\n".join(f"- {point}" for point in summary))

    bullets = "\n".join(f"- {point}" for point in summary)
    write_summary(f"Opened PR with fixes across {len(corrected_files)} file(s):\n\n{bullets}")


if __name__ == "__main__":
    main()
