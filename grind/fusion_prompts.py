"""Prompts and utilities for the fusion judge agent."""

import json
import re
from dataclasses import dataclass
from grind.models import FusionConfig, AgentOutput, FusionDecision


FUSION_SYSTEM_PROMPT = """You are a code review judge comparing multiple implementations of the same task.

Your role is to:
1. Review N agent implementations that all attempted the same task
2. Analyze their approaches, code quality, and correctness
3. Select the best implementation OR synthesize a hybrid combining the best parts
4. Output structured JSON with your decision and reasoning

You must be objective, thorough, and focus on:
- Correctness: Does the code solve the problem correctly?
- Code quality: Is it clean, maintainable, and follows best practices?
- Completeness: Does it handle edge cases and requirements?
- Efficiency: Is the implementation performant?

Your output MUST be valid JSON matching the expected schema."""


FUSION_USER_PROMPT_TEMPLATE = """# Task: Code Review Judge

## Original Task
All agents worked on this task:
```
{original_prompt}
```

## Verification Command
Success is measured by: `{verify_command}`

## Agent Implementations

{agent_outputs}

## Your Decision Strategy
Strategy mode: **{strategy}**

{strategy_guidance}

## Output Requirements

You MUST output valid JSON matching this schema:
```json
{output_schema}
```

### Field Descriptions:
- **decision**: Must be "best-pick", "hybrid", or "none-viable"
  - "best-pick": One agent's solution is clearly superior
  - "hybrid": Combine best parts from multiple agents
  - "none-viable": All solutions have critical flaws

- **selected_agents**: List of agent IDs to use
  - For "best-pick": Single agent ID (e.g., ["agent-1"])
  - For "hybrid": Multiple agent IDs (e.g., ["agent-1", "agent-2"])
  - For "none-viable": Empty list []

- **reasoning**: Detailed explanation of your decision (2-4 sentences)
  - What made the selected solution(s) better?
  - What were the key differentiators?
  - For hybrid: Why combine these specific agents?

- **confidence**: Float between 0.0 and 1.0
  - How confident are you in this decision?
  - 0.9+ : Very confident, clear winner
  - 0.7-0.9: Confident, some trade-offs
  - 0.5-0.7: Moderate, close call
  - <0.5: Low confidence, all solutions have issues

- **hybrid_instructions**: Only for "hybrid" decision
  - Map of agent_id -> list of file paths to take from that agent
  - Example: {{"agent-1": ["file1.py", "file2.py"], "agent-2": ["file3.py"]}}
  - null for "best-pick" or "none-viable"

Output ONLY the JSON, no markdown formatting or extra text."""


def build_fusion_prompt(config: FusionConfig, agent_outputs: dict[str, AgentOutput]) -> str:
    """Build the complete fusion prompt from config and agent outputs.

    Args:
        config: FusionConfig with task details and strategy
        agent_outputs: Dict mapping agent_id -> AgentOutput

    Returns:
        Complete formatted prompt for the fusion judge agent
    """
    # Format agent outputs section
    agent_sections = []
    for agent_id, output in sorted(agent_outputs.items()):
        status = output.result.status if output.result else "unknown"
        files = ", ".join(output.files_changed) if output.files_changed else "No files changed"

        section = f"""### {agent_id}
**Status**: {status}
**Files Changed**: {files}
**Summary**: {output.summary or "No summary provided"}

**Diff**:
```diff
{output.diff or "No changes"}
```
"""
        agent_sections.append(section)

    agent_outputs_text = "\n".join(agent_sections)

    # Strategy-specific guidance
    strategy_guidance = {
        "best-pick": "Select the single best implementation. Set decision='best-pick' and selected_agents to a single agent ID.",
        "hybrid": "Combine the best parts from multiple agents. Set decision='hybrid', list all agents to use in selected_agents, and provide hybrid_instructions mapping each agent to their file paths.",
        "manual": "Analyze all solutions and recommend the best approach. You can choose 'best-pick' or 'hybrid' based on your analysis."
    }

    guidance = strategy_guidance.get(config.strategy, strategy_guidance["manual"])

    # Output schema
    output_schema = {
        "decision": "best-pick | hybrid | none-viable",
        "selected_agents": ["agent-1"],
        "reasoning": "Detailed explanation of why this solution is best...",
        "confidence": 0.85,
        "hybrid_instructions": None  # or {"agent-1": ["file1.py"], "agent-2": ["file2.py"]}
    }

    return FUSION_USER_PROMPT_TEMPLATE.format(
        original_prompt=config.prompt,
        verify_command=config.verify,
        agent_outputs=agent_outputs_text,
        strategy=config.strategy,
        strategy_guidance=guidance,
        output_schema=json.dumps(output_schema, indent=2)
    )


FUSION_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["decision", "selected_agents", "reasoning", "confidence"],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["best-pick", "hybrid", "none-viable"]
        },
        "selected_agents": {
            "type": "array",
            "items": {"type": "string"}
        },
        "reasoning": {
            "type": "string",
            "minLength": 10
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0
        },
        "hybrid_instructions": {
            "type": ["object", "null"],
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            }
        }
    }
}


def parse_fusion_response(response: str) -> FusionDecision:
    """Parse and validate fusion agent response.

    Args:
        response: Raw text response from fusion agent (may contain markdown)

    Returns:
        FusionDecision dataclass with validated decision

    Raises:
        ValueError: If response cannot be parsed or is invalid
    """
    # Try to extract JSON from markdown code blocks or raw text
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        json_text = json_match.group(1)
    else:
        # Try to find JSON object in the text
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_text = json_match.group(0)
        else:
            raise ValueError("No JSON object found in response")

    # Parse JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")

    # Validate required fields
    required_fields = ["decision", "selected_agents", "reasoning", "confidence"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # Validate decision enum
    valid_decisions = ["best-pick", "hybrid", "none-viable"]
    if data["decision"] not in valid_decisions:
        raise ValueError(f"Invalid decision: {data['decision']}. Must be one of {valid_decisions}")

    # Validate selected_agents is a list
    if not isinstance(data["selected_agents"], list):
        raise ValueError(f"selected_agents must be a list, got {type(data['selected_agents'])}")

    # Validate confidence range
    confidence = data["confidence"]
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be a number between 0.0 and 1.0, got {confidence}")

    # Validate reasoning has content
    if not data["reasoning"] or len(data["reasoning"].strip()) < 10:
        raise ValueError("reasoning must be at least 10 characters")

    # Validate hybrid_instructions if present
    hybrid_instructions = data.get("hybrid_instructions")
    if hybrid_instructions is not None:
        if not isinstance(hybrid_instructions, dict):
            raise ValueError(f"hybrid_instructions must be a dict or null, got {type(hybrid_instructions)}")
        # Validate structure: dict[str, list[str]]
        for agent_id, files in hybrid_instructions.items():
            if not isinstance(files, list):
                raise ValueError(f"hybrid_instructions[{agent_id}] must be a list, got {type(files)}")
            if not all(isinstance(f, str) for f in files):
                raise ValueError(f"hybrid_instructions[{agent_id}] must contain only strings")

    # Create FusionDecision dataclass
    return FusionDecision(
        strategy_used=data["decision"],
        selected_agents=data["selected_agents"],
        reasoning=data["reasoning"],
        confidence=float(confidence),
        hybrid_instructions=hybrid_instructions
    )
