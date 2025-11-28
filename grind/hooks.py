from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from grind.logging import log_hook
from grind.models import SlashCommandHook
from grind.utils import Color


async def execute_slash_command(
    client: ClaudeSDKClient,
    command: str,
    verbose: bool = False
) -> tuple[bool, str]:
    if verbose:
        print(Color.info(f"  -> Executing: {command}"))

    try:
        await client.query(command)
        collected = ""
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        collected += block.text
            elif isinstance(msg, ResultMessage):
                log_hook(command, True, collected)
                if verbose:
                    print(Color.success("     Command completed"))
                return (True, collected)
        log_hook(command, False, "No result received")
        return (False, "No result received")
    except Exception as e:
        log_hook(command, False, str(e))
        if verbose:
            print(Color.error(f"     Command failed: {e}"))
        return (False, str(e))


async def execute_hooks(
    client: ClaudeSDKClient,
    hooks: list[SlashCommandHook],
    iteration: int,
    is_error: bool,
    verbose: bool = False
) -> list[tuple[str, str, bool]]:
    results = []
    for hook in hooks:
        if hook.should_run(iteration, is_error):
            success, output = await execute_slash_command(
                client, hook.command, verbose
            )
            results.append((hook.command, output, success))
    return results
