# Grind Loop Architecture

## State Machine

The grind loop operates as a state machine with the following states and transitions:

```mermaid
stateDiagram-v2
    [*] --> Initializing: start

    Initializing --> PreGrindHooks: setup_complete
    PreGrindHooks --> Iterating: hooks_done

    Iterating --> CheckingSignals: response_received
    CheckingSignals --> Complete: GRIND_COMPLETE
    CheckingSignals --> Stuck: GRIND_STUCK
    CheckingSignals --> PostIterationHooks: continue

    PostIterationHooks --> Checkpoint: user_interjected
    PostIterationHooks --> Iterating: no_interject

    Checkpoint --> Iterating: continue
    Checkpoint --> Iterating: guidance_injected
    Checkpoint --> Stuck: abort

    Iterating --> MaxIterations: limit_reached

    MaxIterations --> PostGrindHooks
    Complete --> PostGrindHooks
    Stuck --> PostGrindHooks
    Error --> PostGrindHooks

    PostGrindHooks --> [*]: cleanup

    note right of Iterating: Main loop\\nsends CONTINUE_PROMPT\\nto Claude SDK

    note right of Checkpoint: User can:\\n- Continue\\n- Inject guidance\\n- Abort\\n- Run verify
```

## State Descriptions

| State | Description | Exit Conditions |
|-------|-------------|-----------------|
| Initializing | Setup SDK client, build prompt, start keyboard listener | Setup complete |
| PreGrindHooks | Execute pre_grind slash commands | All hooks executed |
| Iterating | Send prompt to SDK, stream response | Response received |
| CheckingSignals | Parse response for GRIND_COMPLETE/STUCK | Signal found or continue |
| PostIterationHooks | Execute post_iteration hooks | Hooks complete |
| Checkpoint | Interactive pause for user input | User decision |
| Complete | Success exit state | Cleanup |
| Stuck | Agent reports inability to proceed | Cleanup |
| MaxIterations | Iteration limit reached | Cleanup |
| Error | Exception occurred | Cleanup |
