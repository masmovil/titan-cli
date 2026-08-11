# AI Agents

An **agent** wraps AI generation with domain logic: it builds prompts, makes one or more
calls, and turns the answers into something the rest of Titan can use. `PRAgent` writes a
PR description, `IssueGeneratorAgent` writes an issue, `JiraAgent` analyses a ticket.

The rule this document exists to protect:

> **Every agent must run on either transport** — a remote connection or a local CLI —
> chosen by the user per task in AI Configuration, and the agent must not be able to tell
> which one it got.

## The only seam an agent may touch

`BaseAIAgent` depends on the `AIGenerator` protocol (`titan_cli/ai/agents/base.py`):

```python
def generate(messages, max_tokens=None, temperature=None, json_schema=None) -> AIResponse
def is_available() -> bool
```

Two things implement it:

| Implementation | Where | How it generates |
|---|---|---|
| `AIClient` | `titan_cli/ai/client.py` | Calls the configured remote connection |
| `HeadlessGenerator` | `titan_cli/ai/headless_generator.py` | Runs an installed CLI as a subprocess |

**An agent must never import either one**, nor anything under `titan_cli/external_cli/`.
That is what keeps it portable, and it is enforced by
`tests/ai/agents/test_agent_portability.py`, which fails if any module under `agents/`
imports a transport.

Neither a base class nor a contract can give you portability. Only this can.

## Writing an agent

```python
from titan_cli.ai.agents.base import AgentRequest, BaseAIAgent
from titan_cli.ai.agents.contracts import JsonContract, TextContract


class MyAgent(BaseAIAgent):
    def get_system_prompt(self) -> str:
        return "You are an expert at ..."

    def do_the_thing(self, context: str):
        request = AgentRequest(
            context=prompt,
            contract=MY_CONTRACT,
            max_tokens=2000,
            operation="my_operation",   # shows up in logs
        )
        response = self.generate(request)
        return response.parsed          # already the shape the contract declared
```

A step builds it with whatever the router resolved:

```python
match ctx.ai_router.resolve_generator(
    policy=my_step,
    cwd=ctx.git.repo_path if ctx.git else None,
    announce=ctx.textual.ai_chip,
):
    case AIExecutionSuccess(data=generator):
        agent = MyAgent(generator)
    case AIExecutionError(error_code="AI_DISABLED", error_message=message):
        return Skip(message)
    case AIExecutionError(error_message=err):
        return Error(err)
```

and declares both transports — see [workflow-step-rules.md](workflow-step-rules.md):

```python
executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
preferred=[AIProviderType.REMOTE],
```

## Contracts

`contract` is **required** on every `AgentRequest`. You cannot make a call without saying
what shape of answer you expect, which is what stops a new agent from quietly depending on
whatever the model felt like returning.

It lives on the *request*, not on the agent class, because one agent can ask several
different questions — `JiraAgent` makes five calls wanting five different answers.

| Contract | Use it when | Failure behaviour |
|---|---|---|
| `TextContract()` | The answer *is* prose — a commit message, a comment | Never fails, never retries |
| `TextContract(sections=("TITLE", "DESCRIPTION"))` | Named blocks of free text, e.g. a markdown document with a title | A missing section fails |
| `JsonContract(schema=..., required=..., defaults=..., fallback=...)` | Structured data — lists, fields, records | Missing/mistyped required field fails |

**Prose is a legitimate answer, not an escape hatch.** A commit message is one line of
text; declaring `TextContract()` says so honestly, and it works identically on both
transports.

**Do not force markdown into JSON.** A PR description is a whole markdown document; putting
one inside a JSON string is the shape most likely to come back truncated or with mangled
escaping. Use `TextContract(sections=...)` for documents and `JsonContract` for data.

### Defaults decide what a failure costs

- `defaults=None` → a final failure raises `AIResponseParseError`. Use it when the answer
  is the point of the call.
- `defaults={...}` → the call degrades to that value and sets `response.contract_degraded`.
  Use it when the call is additive: a missing risk list makes a thinner report, not a
  failed run.

## The retry

If the answer does not satisfy the contract, `BaseAIAgent` makes **exactly one** repair
call, feeding the previous answer back and asking for the right shape. Then it either
succeeds, degrades to `defaults`, or raises.

This runs on both transports, and **regardless of whether a schema was sent** — which is
the important part, see below.

## A schema is an optimization, never a guarantee

`JsonContract.json_schema()` is forwarded to providers that can enforce one. Today that is
**Claude only**: `supports_structured_output` is `False` for gemini and codex, which accept
the argument and drop it.

Even when it is honored, the answer can still be prose: if the model never invokes the
structured-output tool, the Claude adapter falls back to returning the raw text — with a
**successful exit code**. So:

> Never skip parsing or validation because a schema was sent.

If a future change makes the parse conditional on the schema, gemini and codex break
silently and Claude breaks intermittently.

## What a CLI cannot do

- **`max_tokens` and `temperature` are ignored.** A CLI exposes no such knobs. What bounds
  the answer is the contract, not a token cap.
- **No token accounting.** `response.tokens_used` is `0` on the CLI path. Zero is honest;
  guard any UI that shows it.
- **One subprocess per call.** Measurably ~24s versus 2-5s for a remote call, so an agent
  making five calls takes minutes. That is why `preferred=[REMOTE]` even though both work.

## What a CLI can do that a connection cannot

It runs with `cwd` in the repository, so it can **read the real code** instead of relying
only on what the prompt could afford to include. Tool restrictions
(`AGENT_DISALLOWED_TOOLS`) keep `Read`/`Grep`/`Glob` available while withholding `Edit`,
`Write`, `Bash` and the rest — nobody is watching an agent run, so it must not modify
anything.

**Do not build a transport-conditional prompt around this.** An `if remote / else cli`
branch inside an agent turns one agent into two that drift apart. If a prompt improvement
is worth making, make it on both paths.

## Logging

| Event | Meaning |
|---|---|
| `ai_call_ok` / `ai_call_failed` | One generation attempt (debug) |
| `ai_contract_parse_failed` | The answer missed its shape; a repair is about to run |
| `ai_contract_degraded` | Both attempts failed; the contract's defaults were used |
| `ai_contract_failed` | Both attempts failed with no defaults; raising |
| `ai_agent_cli_ok` / `ai_agent_cli_failed` | The CLI subprocess itself |

Counting `ai_contract_parse_failed` is how you find out whether a contract is actually
holding on a given CLI.
