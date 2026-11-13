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

## Guest image requirements

The image is not bundled with this repository. Provision it on a supported
Linux host and ensure it:

1. Boots from the configured kernel and root filesystem using Firecracker.
2. Works with a read-only root disk.
3. Includes Python 3, Bash, systemd, and the computer guest-agent script at
   `/usr/local/lib/forge/computer_guest.py`.
4. Defines a non-root `computer` user and a systemd service for that agent.
5. Provides `/workspace` as a temporary filesystem limited to the guest
   service, so command-created files do not persist between orchestrator runs.
6. Has no Firecracker network interface configured.

An example systemd unit follows. Adapt the Python path and user/group to the
image; validate the unit on the target distribution before deployment.

The manager binds a guest to one tenant/user/run tuple. Its workspace persists
between computer operations in that run and is discarded when the run
completes or suspends.

```ini
[Unit]
Description=Forge computer guest agent
After=local-fs.target

[Service]
Type=simple
User=computer
Group=computer
WorkingDirectory=/workspace
ExecStart=/usr/bin/python3 /usr/local/lib/forge/computer_guest.py
Restart=always
NoNewPrivileges=yes
PrivateNetwork=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_UNIX AF_VSOCK
TemporaryFileSystem=/workspace:rw,nosuid,nodev,noexec,size=512M

[Install]
WantedBy=multi-user.target
```

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
python -m pytest tests/unit/test_computer.py
```

On a Linux/KVM host with the required executable and guest images, run:

```powershell
python -m pytest tests/integration/test_computer_firecracker.py
```

The integration test skips when KVM, Firecracker, or either image is absent.
On the Windows development host, the expected behavior is an explicit
`COMPUTER_UNAVAILABLE` result rather than local shell execution.
