# Cursor Agent Architecture — Extracted for Learning

Extracted from Cursor v3.5.38 (VS Code 1.105.1 fork) — `cursor-agent-exec` extension (8.2MB webpack bundle)

---

## 1. AGENT LOOP PROTOCOL (agent.v1)

The agent runs a streaming conversation loop. Each turn produces:

```
LLM → plans → ToolCall (with description, approval)
         ↓
    dispatches to executor (shell/read/edit/MCP/browser/grep/etc)
         ↓
    streams back: delta updates in real-time
         ↓
    ToolCallCompleted → LLM gets full result → next turn
```

**Streaming lifecycle for every tool:**
1. `ToolCallStartedUpdate` — "about to run X"
2. `ToolCallDeltaUpdate` + `ThinkingDeltaUpdate` — incremental progress
3. `ShellStreamStdout` / `ShellStreamStderr` — live output chunks
4. `ToolCallCompletedUpdate` — final result

## 2. CORE TOOL TYPES

| Tool | Args | Result | Streaming |
|------|------|--------|-----------|
| `ShellToolCall` | command, working_directory, description | stdout, stderr, exit_code | ✅ ShellStreamStdout/Stderr |
| `EditToolCall` | path, stream_content / StrReplace | file_not_found, permission_denied | ✅ EditToolCallDelta |
| `ReadToolCall` | path, offset, limit, encoding_hint | success (content), error, not_found | No |
| `DeleteToolCall` | path | not_found, busy, permission_denied | No |
| `WebFetchToolCall` | url, tool_call_id | success (markdown), error, rejected | No |
| `McpToolCall` | name, args (map), tool_name, provider_identifier | content[], is_error, structured_content | ✅ |
| `ComputerUseToolCall` | command, sandbox_policy, skip_approval | shell_result | ✅ |
| `GrepToolCall` | pattern, paths | content/file/count results | No |
| `GlobToolCall` | pattern | matching files | No |
| `AskQuestionToolCall` | question, options | answer | Interactive |
| `GenerateImageToolCall` | prompt | image_url | Requires approval |
| `RecordScreenToolCall` | — | video_path | No |
| `ReadLintsToolCall` | path | lint diagnostics | No |
| `ReadTodosToolCall` | — | todo items | No |
| `UpdateTodosToolCall` | todo updates | success | No |
| `PrManagementToolCall` | pr action | registered, needs_confirmation | No |
| `ReflectToolCall` | — | reflection | No |
| `SendFinalSummaryToolCall` | summary | success | No |
| `UpdatePrCodeTourToolCall` | code tour | success | No |
| `EditPrLabelsToolCall` | labels | success | No |

## 3. APPROVAL GATING

Every dangerous operation can be gated by human approval:

```
PreToolUseRequestQuery → human approves/rejects → proceed or cancel
PostToolUseRequestQuery → confirm after execution
PostToolUseFailureRequestQuery → handle error paths

SmartModeApproval — AI auto-approves if classifier says low-risk
HookApprovalRequirement — pre/post hooks that gate execution
SkipApproval flag — bypass gating (for trusted modes)
```

Approval response types per tool:
- `WebSearchRequestResponse.Approved` / `.Rejected`
- `WebFetchRequestResponse.Approved` / `.Rejected`
- `GenerateImageRequestResponse.Approved` / `.Rejected`
- `McpAuthRequestResponse.Approved` / `.Rejected`
- `SwitchModeRequestResponse.Approved` / `.Rejected`
- `SubagentStartRequestResponse` / `SubagentStopRequestResponse`
- `CreatePlanRequestResponse`
- `PostToolUseRequestResponse` / `PostToolUseFailureRequestResponse`
- `PreToolUseRequestResponse` + `PreCompactRequestResponse`

## 4. MCP SNAPSHOT LEASE SYSTEM

Cursor doesn't talk to MCP servers directly — it takes **snapshots**:

```
getMcpSnapshots() → cached tool/resource definitions
McpSnapshotLease (class Zn) — leases server state with snapshotGeneration tracking
SnapshotProvider (class $n) — pulls fresh snapshots, tracks knownGenerations map
```

**Lease selection priority:**
1. Try `cursor-mcp` extension (VSCode lease) — if available, use it
2. Fall back to snapshot lease — `McpSnapshotLease` (class Zn)
3. On change → `onDidChangeMcpSnapshots` fires → diff against `_knownGenerations` → notify consumers

**Key types:**
- `McpToolDefinition` — name, description, input_schema (JSON schema as protobuf Value)
- `McpDescriptor` — serverIdentifier, serverName, plugin, marketplace
- `McpToolDescriptor` — extends tool def with clientKey, providerIdentifier, pluginId
- `McpInstructions` — serverName, instructions
- `McpFileSystemOptions` — per-request filesystem descriptor
- `McpMetaToolOptions` — meta-tool configuration

## 5. REQUEST CONTEXT (what gets sent to the LLM)

The full `RequestContext` message contains everything the model sees:

```
field 2: cursor rules (merged from workspace + user + project)
field 4: environment variables
field 6: git repository info
field 7: tool definitions
field 8-9: conversation notes (listing)
field 11: tracked git repos
field 13: project layouts
field 14: MCP server instructions
field 16: cloud rules
field 17: web search enabled flag
field 18: skill options
field 20: file contents (map of path→content)
field 21: user intent summary
field 22: custom subagents
field 23: MCP filesystem options
field 24: web fetch enabled flag
field 25: hooks additional context
field 28: hooks config
field 29: agent skills
field 30: precomputed human changes
field 32: MCP auth supported flag
field 34: MCP meta-tool options
field 35: read lints enabled
field 37: non-file rules
field 38-45: X_complete flags (lazy loading tracking)
```

## 6. SUBAGENT SYSTEM

Types of subagents:
- `SubagentTypeUnspecified` — default
- `SubagentTypeBash` — bash specialist
- `SubagentTypeBrowserUse` — browser automation
- `SubagentTypeComputerUse` — computer use
- `SubagentTypeCursorGuide` — cursor guide
- `SubagentTypeCustom` — user-defined subagents
- `SubagentTypeDebug` — debugging
- `SubagentTypeExplore` — codebase exploration
- `SubagentTypeMediaReview` — review generated media
- `SubagentTypeShell` — shell commands
- `SubagentTypeVmSetupHelper` — VM environment setup
- `SubagentTypeWatchVideo` — watch screen recordings

Subagent management:
- `SubagentStartRequestQuery/Response` — spawn/kill
- `SubagentAwaitArgs/Result` — wait for subagent completion
- `SubagentPersistedState` — state carried between subagent runs
- `CloudSubagentReference` — cloud-based subagent
- `SubagentModelOverride` — different model per subagent

## 7. SANDBOX MODEL

```
cursorsandbox binary — platform-specific process isolation
  - linux: cursorsandbox
  - darwin: cursorsandbox (same name)
  - win32: cursorsandbox.exe

NetworkPolicy — allow/deny rules per process
SandboxPolicy — sandbox enforcement level
NetworkPolicyLoggingConfig — logging for network access

Network allowlisting:
  - feature gate: mcp_access_network_allowlist
  - default allowlist from dynamic config: sandbox_default_network_allowlist
  - per-team allowlist/denylist
  - local sandbox.json polling via FileSystemWatcher
```

## 8. SHELL EXECUTION

```
ShellCommandParser — parses commands into executable parts
  - ShellCommand
  - ShellCommandAction
  - ShellCommandParsingResult.ExecutableCommand + Args + Redirect

Terminal.exec — PTY-based shell execution
  - TerminalMetadata with Command history
  - TmuxSession support
  - BackgroundShellSpawnArgs/Result — manage background processes

Legacy terminal vs new terminal:
  - Feature gate: useLegacyTerminalTool
  - Legacy: shell mode with ShellCommandParser
  - New: PTY-based with stdio streams

Shell output management:
  - ShellOutputNotificationConfig
  - ShellOutputDeltaUpdate
  - Backpressure config (bufferOutputEvents, flushInterval, maxBufferedBytes)
  - Output suppression (windowMs, thresholdCharsPerSecond)
```

## 9. CANVAS RUNTIME (React Mini-App Server)

The canvas is an in-editor webview that runs React mini-apps:

```
canvas-runtime.esm.js (1.5MB)
  - React 19.2.4, ReactDOM 19.2.4
  - Shiki code highlighter (syntax highlighting in-canvas)
  - Custom UI primitives: DiffView, TodoList, UsageBar, Badge, Pill, Chip
  - Color palette system with CSS variables
  - Theme-aware (dark/light/hc)

mountCanvas(moduleUrl) — main entry point
  - imports React component from URL
  - mounts into #root via createRoot
  - applies theme via CanvasShell + applyBodyTheme
  - error boundary catches crashes → reports to host

Canvas actions (IPC from canvas to IDE):
  - openAgent — opens agent by conversation ID
  - newComposerChat — starts a new composer chat
  - CanvasChevron, CanvasTodoListItem, etc.
```

## 10. AGENT SKILLS & RULES SYSTEM

```
MergedAgentSkillsService (class NB):
  - merges skills from workspace + user + plugins
  - lazy-loaded via X_complete flags
  - onDidChangeSkills → debounced batch update (300ms)

CursorRulesService (class Px):
  - merges rules from workspace, user, IDE, plugins
  - onDidChangeRules → debounced batch update (4s)
  - `updateCursorRules()` / `updateCursorRulesInBatches()` (feature gated)
  - Reload via registerCursorRulesProvider

Agent Skills (protocol):
  - AgentSkill — name, description, content
  - SkillDescriptor — metadata
  - SkillOptions — configuration
  - CursorRule — file globs, content, type (global/file/manual/agent-fetched)
```

## 11. KEY ARCHITECTURAL PATTERNS TO REIMPLEMENT

If building a similar agent system, copy these patterns:

### A. Streaming Tool Lifecycle
Every tool → started→delta→completed events. The UI can show "thinking" then "typing" then "done" for every tool call. No polling, no "wait for response."

### B. MCP Snapshot Caching
Don't call MCP servers on every request. Snapshot their tool definitions with generation tracking, re-fetch only on change, cache with generation diffs.

### C. Approval Gate Pattern
Three-tier: smart mode (auto-approve safe ops) → pre-tool query (check before exec) → post-tool query (confirm after). Each tool declares its approval requirements.

### D. Context Lazy Loading
The RequestContext has `X_complete` flags for every section (rules_complete, env_complete, repo_complete, etc.). Build context incrementally — only load what the model needs for this turn.

### E. Subagent as Tool
Subagents are just another tool type. The agent calls `SubagentStart` → gets back a handle → polls with `SubagentAwait` → gets result. Same streaming lifecycle as shell/read/edit.

### F. Sandbox per Process
Every shell command runs through a sandbox binary with network policy enforcement. Not "sandbox the agent" — sandbox each individual tool execution with its own allow/deny rules.

---

## What We Can Build With This

The full protobuf schema, the streaming protocol, the MCP snapshot lease pattern, the approval gate system, the subagent model, the sandbox architecture, and the canvas runtime — it's all here to learn from and reimplement under our own license.

Next steps:
- A) Build a standalone agent loop in Python/TS that implements this streaming protocol
- B) Build an MCP snapshot proxy that caches tool definitions with generation tracking
- C) Build a sandbox runner with network policies
- D) Port the canvas UI primitives to a standalone component library
