"""Classes for controlling a VM or container."""

import os
import tarfile
import time
from abc import ABC, abstractmethod
from io import BytesIO, StringIO
from typing import Any, BinaryIO, Optional, TextIO, Union

import fabric
import invoke


class RemoteController(ABC):
    """Base class for controlling either a VM or container."""

    @abstractmethod
    def run(self, command, pty, **kwargs):
        """Run a command."""

    @abstractmethod
    def put(self, local, remote):
        """Add a file to the remote filesystem."""


class ContainerController(RemoteController):
    """
    Controller for a container hosted remotely or locally.

    Can start the continer, run commands within, move files from the local to the
    container filesystem.
    """

    def __init__(
        self,
        name: str,
        container_image: str,
        jump_host: Optional[invoke.Context] = None,
    ) -> None:
        """Prepare a container for remote control."""
        self.name = name
        self.container_image = container_image
        self.context = jump_host or invoke.context.Context()

    def start(self):
        """Start a container with a never-ending process."""
        if self.container_image == "docker:dind":
            self.context.run(
                f"docker run --privileged --user root --name {self.name} --detach {self.container_image}",
                in_stream=False,
            )
        else:
            self.context.run(
                f"docker run --user root --name {self.name} --detach {self.container_image} sleep infinity",
                in_stream=False,
            )

    def run(
        self, command: str, pty: bool = False, **kwargs: Any
    ) -> Optional[invoke.runners.Result]:
        """Run a command in the running container."""
        docker_options = "--interactive --tty" if pty else ""
        docker_cmd = f"docker exec --user root {docker_options} {self.name}"

        return self.context.run(f"{docker_cmd} {command}", pty=pty, **kwargs)

    def put(
        self, local: Union[str, TextIO, BinaryIO], remote: Optional[str] = None
    ) -> Optional[invoke.runners.Result]:
        """Upload a file from the local filesystem to the container."""
        # Builds a tar archive in memory before uploading

        if remote is not None:
            remote_path, remote_name = os.path.split(remote)
        else:
            remote_path, remote_name = ("", "")

        if remote_name == "" and isinstance(local, str):
            remote_name = os.path.basename(local)
        if remote_path == "":
            remote_path = "."

        if isinstance(local, str):
            with open(local, "rb") as f:
                file_data = f.read()
        elif isinstance(local, StringIO):
            file_data = local.read().encode("utf-8")
        elif isinstance(local, BytesIO):
            file_data = local.read()
        else:
            file_data = b""

        pw_tarstream = BytesIO()
        pw_tar = tarfile.TarFile(fileobj=pw_tarstream, mode="w")
        tarinfo = tarfile.TarInfo(name=remote_name)
        tarinfo.size = len(file_data)
        tarinfo.mtime = int(time.time())
        pw_tar.addfile(tarinfo, BytesIO(file_data))
        pw_tar.close()
        pw_tarstream.seek(0)
        from invoke.runners import Runner

        Runner.input_sleep = 0

        return self.context.run(
            f"docker exec --interactive {self.name} tar x -C {remote_path} -f -",
            in_stream=pw_tarstream,
        )

    def remove(self):
        return self.context.run(f"docker rm --force {self.name}", in_stream=False)


class VMController(RemoteController):
    """
    VMController class.

    Handles controlling the connection to a remote VM and running all commands thereon.
    """

    def __init__(self, name: str, ip_address: str, user: str, keyfile: str) -> None:
        """Initialize."""
        self.name = name
        self.ip_address = ip_address
        self.user = user
        self.keyfile = keyfile
        try:
            self.ssh_connection = fabric.Connection(
                self.ip_address,
                user=self.user,
                connect_kwargs={"key_filename": [self.keyfile]},
            )
        except AttributeError as error:
            raise ConnectionError(
                "Couldn't connect to " + self.name + " VM."
            ) from error

    def run(
        self, command: str, pty: bool = False, **kwargs: Any
    ) -> invoke.runners.Result:
        """
        Run a command on VM.

        Provides a subset of functionality from
        http://docs.pyinvoke.org/en/latest/api/runners.html#invoke.runners.Runner.run
        """
        try:
            return self.ssh_connection.run(command, warn=True, pty=pty, **kwargs)
        except AttributeError as error:
            raise ConnectionError(
                "Couldn't connect to " + self.name + " VM."
            ) from error

    def put(
        self, local: Union[str, TextIO, BinaryIO], remote: Optional[str] = None
    ) -> fabric.transfer.Result:
        """
        Upload a file from the local filesystem to VM.

        See https://docs.fabfile.org/en/2.6/api/transfer.html#fabric.transfer.Transfer.put
        """
        try:
            self.ssh_connection.put(local)
        except AttributeError as error:
            raise ConnectionError(
                "Couldn't connect to " + self.name + " VM."
            ) from error

    def remove(self, path: str) -> None:
        """
        Remove the file at the given path on VM.

        See http://docs.paramiko.org/en/latest/api/sftp.html#paramiko.sftp_si.SFTPServerInterface.remove
        """
        try:
            self.ssh_connection.sftp().remove(path)
        except AttributeError as error:
            raise ConnectionError(
                "Couldn't connect to " + self.name + " VM."
            ) from error
