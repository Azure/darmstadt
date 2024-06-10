"""Classes for setting up a connection to a remote container or VM."""

import logging
import random
import socket
from typing import Any, Callable, Optional, Tuple

import docker
import fabric
import invoke
import paramiko

logging.captureWarnings(True)


def _remote_docker_connection(hostname):
    return docker.from_env(environment={"DOCKER_HOST": f"ssh://{hostname}"})


class JumpHost:
    """A connection to a remote box offering SSH and running docker."""

    def __init__(
        self,
        host,
        connection_func=fabric.Connection,
        docker_client_func=_remote_docker_connection,
    ):
        """Set up connection parameters."""
        self.host = host
        self.connection_func = connection_func
        self.docker_client_func = docker_client_func

        self.cached_docker_client = None
        self.cached_connection = None

    def __str__(self):
        """String representation of the host is the hostname."""
        return self.host

    @classmethod
    def choose_from(cls, *default_hosts, override=None):
        """Select a jump host.

        A selection of default hosts to try can be provided. If so, and no
        override is given, then we connect to a random host from the list.

        If the connection fails, then we cycle through available hosts.

        If override is set, then it is either an index (1-based) of the hosts
        or a hostname itself. There is no fallback behaviour in this case.
        """
        if isinstance(override, int) or (
            isinstance(override, str) and override.isnumeric()
        ):  # Index of desired host provided
            # Override index starts at 1
            return default_hosts[int(override) - 1]
        elif override is not None:
            # Hostname of desired host provided
            return JumpHost(override)

        default_host_list = list(default_hosts)
        random.shuffle(default_host_list)
        host, _ = cls.try_function_on_any(lambda jh: jh.connect(), *default_host_list)
        return host

    @classmethod
    def try_connect_to_any(
        cls, *jump_hosts: "JumpHost"
    ) -> Tuple["JumpHost", fabric.Connection]:
        """Returns a jump_host from the argument list that connected."""
        return cls.try_function_on_any(lambda jh: jh.connect(), *jump_hosts)

    @classmethod
    def try_function_on_any(
        cls, func: Callable[["JumpHost"], Any], *jump_hosts: "JumpHost"
    ) -> Tuple["JumpHost", Any]:
        """
        Attempt to run a function on a jump host, with failover.

        If the function throws an exception, then failover to the next host in the list.
        """
        successful_host: Optional["JumpHost"] = None
        last_exception: Optional[Exception] = None

        for host in jump_hosts:
            try:
                result = func(host)
            except ConnectionError as e:
                last_exception = e
                logging.warning(
                    "ConnectionError when connecting to %s, caused by %s", host, e
                )
                continue
            except Exception as e:  # pylint: disable=broad-except
                last_exception = e
                logging.warning(
                    "Exception when connecting to %s, caused by %s", host, e
                )
                continue

            successful_host = host
            break
        else:
            logging.error("Unable to connect to any jump hosts.")
            if last_exception:
                raise last_exception
            raise Exception("No hosts provided")

        if successful_host:
            return successful_host, result
        raise Exception("Unreachable code.")

    def connect(self) -> fabric.Connection:
        """
        Connect to jump host over SSH.

        Returns a fabric.Connection instance to the jump host.

        Raises ConnectionError for a variety of known failure modes.
        """
        if self.cached_connection is not None:
            return self.cached_connection

        try:
            connection = self.connection_func(self.host)
            connection.open()
        except socket.gaierror as e:
            logging.error("DNS lookup error when connecting to %s", self.host)
            raise ConnectionError from e
        except socket.timeout as e:
            logging.error("SSH timeout when connecting to %s", self.host)
            raise ConnectionError from e
        except paramiko.AuthenticationException as e:
            logging.error("SSH authentication failed when connecting to %s", self.host)
            raise ConnectionError from e

        logging.debug("Successfully connected to %s", self.host)
        self.cached_connection = connection
        return connection

    def docker_client(self) -> docker.DockerClient:
        """
        Connect a docker client to docker running on the jump host.

        Returns a docker.DockerClient instance.

        Raises ConnectionError for a variety of known failure modes.
        """
        if self.cached_docker_client is not None:
            return self.cached_docker_client

        try:
            client = self.docker_client_func(self.host)
        except socket.gaierror as e:
            logging.error("DNS lookup error when connecting to %s", self.host)
            raise ConnectionError from e
        except TimeoutError as e:
            logging.error("SSH timeout when connecting to %s", self.host)
            raise ConnectionError from e
        except paramiko.AuthenticationException as e:
            logging.error("SSH authentication failed when connecting to %s", self.host)
            raise ConnectionError from e

        logging.debug("Docker client connected to %s", self.host)
        self.cached_docker_client = client
        return client


class LocalHost(JumpHost):
    """Provides the same functionality as JumpHost, but for a local connection."""

    def __init__(self):
        """Dummy initialiser."""
        super().__init__("losalhost")

    def connect(self):
        """Provide a local invoke context."""
        return invoke.context.Context()

    def docker_client(self):
        """Provide a docker client to a local docker server."""
        return docker.from_env()
