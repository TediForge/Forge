# Caller-Owned External Tools

The orchestrator owns local execution only. External services and credentials
belong to the caller. Supply caller-owned functions using `tools`; the engine
suspends with a `function_call`, and the caller executes the function and
resumes with `previous_response_id` and a `function_call_output` item inside
`messages`.

## Define a tool

Each definition contains a one-word lowercase `name`, description, and JSON
Schema parameters:

```json
{
  "type": "function",
  "name": "issue",
  "description": "Create a GitHub issue when the user asks to file a bug or feature request.",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "body": {"type": "string"}
    },
    "required": ["title"],
    "additionalProperties": false
  }
}
```

The `description` and `parameters` are sent to the model. The orchestrator
validates the name against local-tool collisions and uses the schema to plan a
call; it does not load an adapter or service credential.

## Execute and resume

1. Include the function definition in the initial request's `tools`.
2. When the response status is `requires_action`, inspect its
   `functionCalls`. Each call contains `call_id`, `name`, and JSON-string
   `arguments`.
3. Execute the call in the caller's own adapter, applying the caller's
   credentials and policy.
4. Resume with `previous_response_id` and one `function_call_output` message
   containing the matching `call_id` and an `output` value.
5. Do not send API credentials or service tokens to the orchestrator.

Example resume output:

```json
{
  "previous_response_id": "run_abc123",
  "messages": [
    {"type": "function_call_output", "call_id": "call_123456", "output": "{\"number\":42}"}
  ]
}
```

The two-phase suspension/resume contract is specified by
[D-004](../decisions/D-004-external-tools-two-phase-resume.md).

## Caller-owned stateful capabilities

The built-in `todo` and `memory` tools were removed under
[D-022](../decisions/D-022-no-stateful-tools.md). If an application needs
durable tasks or memory, it must define those as external tools and execute
them against its own store. The caller owns persistence, retention, and tenant
isolation; the orchestrator only plans, suspends, and resumes the call.

For example, the caller can include a `todo` function schema in `tools`:

```json
{
  "messages": [
    {"role": "user", "content": "Add 'buy milk' to my todo list"}
  ],
  "tools": [{
    "type": "function",
    "name": "todo",
    "description": "Manage the user's todo list using the caller-owned store.",
    "parameters": {
      "type": "object",
      "properties": {
        "operation": {"type": "string", "enum": ["add", "list", "complete", "delete"]},
        "text": {"type": "string"},
        "task_id": {"type": "string"}
      },
      "required": ["operation"],
      "additionalProperties": false
    }
  }]
}
```

The caller handles the returned `function_call` with its own implementation,
then supplies the result as `function_call_output` when resuming. `memory`
can be supplied the same way. Neither capability is registered as a local
tool or backed by an orchestrator-managed cache.

## Skills

The caller may provide its own service-specific skill alongside its tool
schema. That skill belongs in the caller's codebase. The orchestrator does not
ship skills for external services.
