"""Build a bootable Firecracker ext4 root filesystem from a JSON manifest."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from orchestrator.computer.images.loader import ComputerImageManifest, load_manifest


_IMAGE_DIRECTORY = Path(__file__).parent
_DOCKERFILE_TEMPLATE = _IMAGE_DIRECTORY / "Dockerfile.base"
_ROOTFS_SIZE_MB = 4096


def _runtime_repositories(manifest: ComputerImageManifest) -> str:
    commands: list[str] = []
    if manifest.runtimes.python:
        commands.append("add-apt-repository -y ppa:deadsnakes/ppa")
    if manifest.runtimes.php:
        commands.append("add-apt-repository -y ppa:ondrej/php")
    if manifest.runtimes.node:
        version = manifest.runtimes.node.version
        commands.append(
            "install -d -m 0755 /etc/apt/keyrings "
            "&& curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key "
            "-o /tmp/nodesource.gpg.key "
            "&& gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg "
            "/tmp/nodesource.gpg.key "
            "&& echo "
            + shlex.quote(
                f"deb [arch=amd64 signed-by=/etc/apt/keyrings/nodesource.gpg] "
                f"https://deb.nodesource.com/node_{version}.x nodistro main"
            )
            + " > /etc/apt/sources.list.d/nodesource.list "
            "&& rm -f /tmp/nodesource.gpg.key"
        )
    if not commands:
        return "RUN true"
    return "RUN " + " \\\n    && ".join(commands)


def _runtime_packages(manifest: ComputerImageManifest) -> list[str]:
    packages: list[str] = []
    if runtime := manifest.runtimes.python:
        packages.extend(("python3.11", "python3.11-venv"))
    if runtime := manifest.runtimes.node:
        packages.append("nodejs")
    if runtime := manifest.runtimes.php:
        packages.append(f"php{runtime.version}-cli")
        packages.extend(f"php{runtime.version}-{extension}" for extension in runtime.extensions)
        if runtime.composer:
            packages.append("composer")
    return sorted(set(packages))


def _runtime_package_install(manifest: ComputerImageManifest) -> str:
    packages = _runtime_packages(manifest)
    if not packages:
        return "RUN true"
    return (
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        + shlex.join(packages)
        + " && rm -rf /var/lib/apt/lists/*"
    )


def _runtime_setup(manifest: ComputerImageManifest) -> str:
    commands: list[str] = []
    if runtime := manifest.runtimes.python:
        setup = "python3.11 -m venv /opt/forge-python"
        if runtime.global_pip:
            setup += (
                " && /opt/forge-python/bin/python -m pip install --no-cache-dir "
                + shlex.join(runtime.global_pip)
            )
        setup += (
            " && ln -s /opt/forge-python/bin/python /usr/local/bin/python3 "
            "&& ln -s /opt/forge-python/bin/python /usr/local/bin/python"
        )
        commands.append(setup)
    if runtime := manifest.runtimes.node:
        if runtime.global_npm:
            commands.append("npm install --global " + shlex.join(runtime.global_npm))
    if not commands:
        return "RUN true"
    return "RUN " + " \\\n    && ".join(commands)


def _generate_dockerfile(manifest: ComputerImageManifest) -> str:
    template = _DOCKERFILE_TEMPLATE.read_text(encoding="utf-8")
    go_stage = ""
    go_runtime = ""
    if manifest.runtimes.go:
        version = manifest.runtimes.go.version
        go_stage = f"FROM golang:{version} AS forge-go\n"
        go_runtime = "COPY --from=forge-go /usr/local/go /usr/local/go"
    replacements = {
        "{{SYSTEM_PACKAGES}}": shlex.join(manifest.system_packages),
        "{{RUNTIME_REPOSITORIES}}": _runtime_repositories(manifest),
        "{{RUNTIME_PACKAGE_INSTALL}}": _runtime_package_install(manifest),
        "{{GO_RUNTIME}}": go_runtime,
        "{{RUNTIME_SETUP}}": _runtime_setup(manifest),
        "{{USER_UID}}": str(manifest.user.uid),
        "{{USER_NAME}}": shlex.quote(manifest.user.name),
        "{{USER_NAME_SED}}": manifest.user.name,
        "{{USER_UID_SED}}": str(manifest.user.uid),
        "{{DIRECTORIES}}": shlex.join(manifest.directories),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    if "{{" in template or "}}" in template:
        raise ValueError("Dockerfile template contains an unresolved placeholder")
    return go_stage + template


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required image-build command is unavailable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Image-build command failed: {command[0]} (exit {exc.returncode})") from exc


def build_rootfs(manifest_name: str, output_path: Path) -> Path:
    """Build a 4 GiB sparse ext4 rootfs. Requires Linux, Docker, and root privileges."""
    manifest = load_manifest(manifest_name)
    return _build_rootfs(manifest, output_path)


def _build_rootfs(manifest: ComputerImageManifest, output_path: Path) -> Path:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Building an ext4 root filesystem requires a Linux host")
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise RuntimeError("Building and mounting the ext4 root filesystem requires root privileges")

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fd, temporary_image_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(output_fd)
    temporary_image_path = Path(temporary_image_name)
    try:
        with tempfile.TemporaryDirectory(prefix="forge-computer-image-") as temp_dir:
            temporary = Path(temp_dir)
            docker_context = temporary / "context"
            docker_context.mkdir()
            dockerfile_path = docker_context / "Dockerfile"
            archive_path = temporary / "rootfs.tar"
            image_path = temporary_image_path
            mount_path = temporary / "mount"
            mount_path.mkdir()
            dockerfile_path.write_text(_generate_dockerfile(manifest), encoding="utf-8")
            shutil.copyfile(Path(__file__).parents[1] / "guest.py", docker_context / "computer_guest.py")
            shutil.copyfile(
                _IMAGE_DIRECTORY / "forge-computer-agent.service",
                docker_context / "forge-computer-agent.service",
            )

            container_id: str | None = None
            mounted = False
            try:
                _run([
                    "docker", "build", "--platform=linux/amd64",
                    "--tag", f"forge-computer:{manifest.name}",
                    "--file", str(dockerfile_path), str(docker_context),
                ])
                try:
                    container_id = subprocess.check_output(
                        ["docker", "create", f"forge-computer:{manifest.name}"],
                        text=True,
                    ).strip()
                except FileNotFoundError as exc:
                    raise RuntimeError("Required image-build command is unavailable: docker") from exc
                except subprocess.CalledProcessError as exc:
                    raise RuntimeError(
                        f"Docker could not create the image container (exit {exc.returncode})"
                    ) from exc
                if not container_id:
                    raise RuntimeError("Docker did not return a container ID for the image")
                _run(["docker", "export", "--output", str(archive_path), container_id])

                _run(["truncate", "--size", f"{_ROOTFS_SIZE_MB}M", str(image_path)])
                _run(["mkfs.ext4", "-F", "-L", "forge-root", str(image_path)])
                _run(["mount", "-o", "loop,rw", str(image_path), str(mount_path)])
                mounted = True
                _run(["tar", "-xpf", str(archive_path), "-C", str(mount_path)])
                _run(["sync"])
                _run(["umount", str(mount_path)])
                mounted = False
                os.replace(image_path, output_path)
            finally:
                try:
                    if mounted:
                        _run(["umount", str(mount_path)])
                finally:
                    try:
                        if container_id is not None:
                            _run(["docker", "rm", "--force", container_id])
                    finally:
                        if temporary_image_path.exists():
                            temporary_image_path.unlink()
    finally:
        if temporary_image_path.exists():
            temporary_image_path.unlink()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="base", help="Bundled image manifest name")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/computer-images/base.ext4"),
        help="Destination ext4 image path",
    )
    args = parser.parse_args()
    result = build_rootfs(args.manifest, args.output)
    print(f"Root filesystem built at {result}")


if __name__ == "__main__":
    main()
