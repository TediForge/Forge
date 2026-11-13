# D-026: Isolate Computer Commands in Disposable Firecracker MicroVMs

- **Status:** Accepted
- **Date:** 2026-11-12
- **Owner:** Orchestrator
- **Related:** [D-019](./D-019-one-tool-per-domain-one-skill.md), [D-020](./D-020-uniform-operation-field.md), [D-021](./D-021-no-registered-placeholder-operations.md)

## Context

Local tools use a host-side workspace path policy in
`orchestrator/computer/workspace.py`; it is not an operating-system isolation
boundary for shell execution. Adding general command execution to the
Orchestrator process would expose the host and its credentials to
model-generated commands. The computer capability therefore requires an
independently enforced guest boundary and a narrow host/guest protocol.

## Decision

Register one `computer` tool with `execute`, `read_file`, and `write_file`
operations. All three operate through a disposable Firecracker microVM. The
Orchestrator never falls back to running a command on the host.

- Firecracker is launched locally and configured through its Unix-domain
  socket API. The host must be Linux with `/dev/kvm`.
- The guest root disk is attached read-only and the guest agent runs as an
  unprivileged user. `/workspace` is temporary storage scoped to the guest
  service. No network interface is configured for the VM.
- Commands and output have code-owned time and size limits. File operations
  accept workspace-relative paths only and enforce a file-size limit.
- The default pool maintains five warm guests and is capped at 200, subject
  to a host/cgroup-memory-derived limit with a 512 MiB host reserve. Requests
  wait up to 30 seconds at capacity. These limits are code-owned.
  A lease is scoped to one tenant, user, and orchestrator run, so operations
  in that run can share the guest workspace without sharing it across
  identities. The VM is destroyed when the run completes or suspends; a
  replacement is booted for the warm pool. Same-run operations are serialized.
  The system is bounded by the configured pool and host memory; support for
  one million instances is not claimed.
- Kernel and root filesystem images are deployment-provisioned at the
  code-owned default paths. Pool and guest sizing overrides are passed through
  `ComputerConfig` in code; no `.env` variables are added.
- Local file tools continue to use the host-side workspace path policy in
  `computer/workspace.py`; it is not a substitute for guest isolation.
- Screenshot and GUI operations are not registered until a GUI guest runtime
  and display-capture policy are implemented.
- Snapshot cloning is not enabled. Firecracker warns that restoring the same
  snapshot concurrently can duplicate guest entropy and identity. The runtime
  has no guest-side reseeding and identity-reset protocol, so it continues to
  cold-boot instances instead of weakening tenant isolation. See the upstream
  [snapshot security guidance](https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md#snapshot-security-and-uniqueness).
- VM lifecycle records include tenant, user, run, and instance identifiers.
  Unassigned warm-pool provisioning uses the `system` identity.

## Consequences

- A computer request fails explicitly with `COMPUTER_UNAVAILABLE` when
  Firecracker, KVM, the guest image, or the guest agent is unavailable.
- A host without Linux/KVM can run unit tests, but cannot execute a real
  computer integration test.
- Run-scoped guests support multiple serialized operations in one run while
  preventing cross-run state sharing, but incur boot and replacement cost.
  Autoscaling is bounded and depends on host memory; million-instance scale
  and snapshot latency are not promised.
- Shell-command checks are defense in depth; the VM, guest privilege boundary,
  read-only root disk, and absent network device are the isolation boundary.
- `D-021` remains in force for host-process shell execution.

## Validation

- Unit tests cover policy, dispatch, cancellation cleanup, tenant isolation,
  bounded scaling, acquisition timeout, and lifecycle audit records.
- A Linux/KVM integration test runs three guest leases concurrently and
  verifies command output and separate workspace files when the Firecracker
  executable and prepared images are installed.
