# Prompt and invocation contract

1. A short shared instruction states musical intent, task routing, silent/source
   preservation, bounded changes, native capability boundaries and evidence limits.
   Simple one-step reads may go directly to their tool; preparation is once per
   new multi-step production task, not a repeated mandatory call.
2. A pure preparation tool returns a task-specific plan without connecting to
   Live, reading/rendering audio, scanning plugins, consulting the network or
   changing a ledger. It accepts strict bounded task metadata and relative path
   hints; it returns only available tools for that server configuration.
3. File analysis/mixing/mastering must not require Live status. Native inspection
   must begin with status. Missing assets produce explicit blockers plus useful
   independent context requests, never an invented input or automatic mutation.
4. Retrieve at most two relevant methods and three recalled events initially.
   Do not load the whole index, ledger or plugin inventory. Query a plugin only
   when requested. Artist examples remain optional. Retained content is context,
   not permission or an instruction to execute unrelated actions.
5. Register an explicit reusable MCP prompt with the same builder. MCP prompts
   are user/client selected; do not claim they automatically run for every call.
   Server instructions and tool descriptions provide discoverable entry guidance.
   Preserve native read-only tool compatibility. A workspace adds one preparation
   tool to the existing18. No new rendering or transport capability is added.
6. Retain bounded routing fixtures and actual official-SDK prompt/tool checks.
   Test strict inputs, missing assets, offline routing, plugin context, compose
   limits, prompt selection and response bounds. These are deterministic contract
   checks, not measured model behavior, quality, latency or token-cost improvement.

Shared instruction budget: at most2200characters. Default short briefs: at most
7000characters, measured as characters rather than inferred model tokens. Input
and output have explicit UTF-8 byte limits. Prompt wording is guidance; the existing
software gates enforce supported operations. Model-wide optimality is unproven.
