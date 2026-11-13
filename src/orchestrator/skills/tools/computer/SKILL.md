---
name: computer
description: Use to run a command or manage a file in an isolated Linux microVM; do not use for host files or network access.
category: tool
version: 1.0
---

# Computer

The computer tool runs a bounded operation inside a disposable Firecracker
microVM. Commands do not run in the Orchestrator process. The guest has no
network interface; commands should use only the files and programs included
in the guest image.

## Operations

| operation | What it does | Required arguments | Status |
|---|---|---|---|
| `execute` | Run a shell command from `/workspace` with a time and output limit | `command` | implemented |
| `read_file` | Read a bounded file under `/workspace` | `path` | implemented |
| `write_file` | Write UTF-8 text under `/workspace` | `path`, `content` | implemented |

## When to use

- The user requests a small command-line task in an isolated Linux guest.
- The user asks to create or read a file in the guest workspace.
- The task needs a Linux command that is not available as a local tool.

## When not to use

- The task requires access to the Orchestrator host or its filesystem.
- The command requires internet, private network, or service access.
- The task can be completed using a focused built-in tool such as `data` or `pdf`.
- A task requires a GUI, interactive desktop, browser, or screenshot.

## How to call

Call `computer(operation=..., ...)` and provide only the arguments for that
operation. Paths are relative to `/workspace`; use `outputs/` for files that
the caller needs to retrieve. The guest is retained across computer
operations within one tenant/user/run and destroyed when that run ends.

## Examples

1. **Print text:** `computer(operation="execute", command="printf 'hello\\n'")`.
2. **List workspace files:** `computer(operation="execute", command="find . -maxdepth 2 -type f")`.
3. **Write a note:** `computer(operation="write_file", path="outputs/note.txt", content="Hello")`.
4. **Read a note:** `computer(operation="read_file", path="outputs/note.txt")`.
5. **Create and verify:** write a script under `outputs/`, then execute it with the guest Python interpreter during the same run.
6. **Wrong operation:** an unknown operation returns `INVALID_OPERATION`; select one of the three listed operations.
7. **Outside workspace:** use a relative path under `/workspace`, not a host or absolute path.

## Edge cases

- **Firecracker or KVM unavailable:** report `COMPUTER_UNAVAILABLE`; do not run the command on the host.
- **Guest image or agent unavailable:** report the runtime error; do not claim the operation succeeded.
- **Blocked command:** report `POLICY_VIOLATION`; do not retry an equivalent destructive command.
- **Command timeout:** output is bounded and the guest is destroyed after the lease.
- **Large output or file:** the runtime enforces fixed code-owned limits; split or narrow the request.
- **Binary file:** read output is base64 encoded and marked with `encoding=base64`.
- **Path traversal or absolute path:** report `POLICY_VIOLATION`; keep all paths inside `/workspace`.
- **Network request:** the VM has no network interface; do not try alternate network commands.
- **Missing file:** report the guest error and verify the workspace-relative path.
