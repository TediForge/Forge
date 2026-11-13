# Firecracker Computer Runtime

The `computer` tool runs a command or manages a file in a disposable Linux
microVM. It never falls back to host execution. This optional runtime requires
a Linux host with `/dev/kvm`, an installed Firecracker binary, and a prepared
guest kernel and root filesystem.

## Code-owned configuration

The defaults are defined in
[`src/orchestrator/computer/config.py`](../../src/orchestrator/computer/config.py):

- Firecracker: `/usr/local/bin/firecracker`
- Kernel: `/var/lib/firecracker/vmlinux.bin`
- Root filesystem: `/var/lib/firecracker/rootfs.ext4`
- Warm pool: five guests; maximum 200 concurrent instances, further capped
  using detected host/cgroup memory with a 512 MiB reserve
- Scale threshold: 20% of the warm pool
- Acquisition timeout: 30 seconds when the pool is at capacity
- Guest memory/vCPUs: 1024 MiB / two
- Command time: 30 seconds; command output and file size: 1 MiB

No environment variables are used for this runtime. A deployment that needs
different paths or limits can pass a `ComputerConfig` to `ComputerManager` in
code. Legacy `pool_size` and `max_instances` constructor arguments remain
supported. The pool is bounded and does not support million-instance scaling.
When the configured pool limit is reached, new requests wait for available
capacity and return `COMPUTER_UNAVAILABLE` after the acquisition timeout.
The manager replenishes the warm pool asynchronously when its available
fraction falls below the configured scale threshold.

## Snapshot status

Snapshot capture and restore are not enabled. Firecracker requires callers to
manage immutable memory/state files and host-resource overrides. More
importantly, Firecracker warns that concurrently restoring the same snapshot
can duplicate guest random state and identifiers. This runtime has no
guest-side reseed and identity-reset protocol, so snapshot cloning would weaken
isolation. Instances continue to be cold-booted and destroyed at run end; no
restore-time target is claimed. See Firecracker's
[snapshot security and uniqueness guidance](https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md#snapshot-security-and-uniqueness).

VM creation and destruction are written to the configured JSONL audit log
with the tenant, user, run, and instance IDs. Warm-pool instances that have
not yet been assigned to a request use the `system` identity.

## Building a guest image

The repository includes strict JSON manifests and a Docker/ext4 builder in
`src/orchestrator/computer/images/`. The `base` manifest specifies Ubuntu
22.04 with Python 3.11, Node.js 20, PHP 8.2, Go 1.22, and common build tools.
The `python-only` manifest is a smaller alternative. The strict loader rejects
unknown fields, unsupported runtime versions, and paths outside `/workspace`
and `/tmp`.

On a Linux host with Docker, `mkfs.ext4`, loop mounts, `tar`, and root
privileges, build the image from the repository root:

```bash
sudo env PYTHONPATH=src python -m orchestrator.computer.images.builder \
  --manifest base \
  --output /var/lib/firecracker/rootfs.ext4
```

Alternatively, run the wrapper from the repository root:

```bash
sudo env PYTHONPATH=src bash src/orchestrator/computer/images/build_rootfs.sh \
  base /var/lib/firecracker/rootfs.ext4
```

The output is a 4 GiB sparse ext4 file; Docker and package
repositories are contacted during image creation. The image is not built
automatically by the Orchestrator, and Docker, mount, and ext4 utilities are
not runtime dependencies.

The builder creates a systemd guest with the non-root user and guest-agent
service expected by Firecracker. It configures the image root disk as
read-only, `/workspace`, `/tmp`, and volatile runtime state as temporary
filesystems, and leaves network interfaces out of the Firecracker
configuration. Install a compatible Linux kernel separately at the configured
`kernel_path`; point `ComputerConfig.rootfs_path` at the generated image if it
is not built at the configured default path.

The manager binds a guest to one tenant/user/run tuple. Its workspace persists
between computer operations in that run and is discarded when the run
completes or suspends. The guest service unit is
`src/orchestrator/computer/images/forge-computer-agent.service`; it runs the
agent as the manifest's unprivileged user.

The guest agent is the host's only command/file protocol. Keep it running as
the unprivileged user; do not grant it host mounts, credentials, or network
access. The root filesystem is mounted read-only by the Firecracker driver.

## Tool operations

- `computer(operation="execute", command="...")` runs Bash in `/workspace`.
- `computer(operation="read_file", path="outputs/result.txt")` reads a
  workspace-relative file.
- `computer(operation="write_file", path="outputs/input.txt", content="...")`
  writes UTF-8 text.

The shell-command checks are defense in depth, not a complete shell parser.
Isolation relies on Firecracker, the guest's unprivileged service, its
read-only root disk, temporary workspace, and lack of a network interface.
GUI and screenshot operations are not implemented.

## Verification

On any platform, run the focused unit tests:

```powershell
python -m pytest tests/unit/test_manifest_loader.py tests/unit/test_computer.py
```

To exercise actual Docker and ext4 rootfs creation, opt in on a Linux host
where Docker works as root and the mount utilities are available:

```bash
FORGE_RUN_ROOTFS_BUILD_TESTS=1 python -m pytest tests/integration/test_rootfs_build.py
```

On a Linux/KVM host with the required executable, kernel, and guest image, run:

```powershell
python -m pytest tests/integration/test_computer_firecracker.py
```

The Firecracker integration test skips when KVM, Firecracker, or either image
is absent. The rootfs build test skips unless explicitly enabled. On the
Windows development host, the expected behavior is an explicit
`COMPUTER_UNAVAILABLE` result rather than local shell execution.
