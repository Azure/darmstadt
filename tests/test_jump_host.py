import socket
from unittest.mock import Mock

import fabric
import paramiko
import pytest

from darmstadt.jump_host import JumpHost, LocalHost

# Set up hosts for testing.
GOOD_HOST_ONE = LocalHost()
GOOD_HOST_TWO = LocalHost()
BAD_HOST_BAD_CODE = JumpHost(
    "fakehost", connection_func=lambda host: mock_connect(ZeroDivisionError)
)
BAD_HOST_TIMEOUT = JumpHost(
    "fakehost",
    connection_func=lambda host: mock_connect(socket.timeout),
    docker_client_func=Mock(side_effect=TimeoutError),
)
BAD_HOST_DNS_FAILURE = JumpHost(
    "fakehost",
    connection_func=lambda host: mock_connect(socket.gaierror),
    docker_client_func=Mock(side_effect=socket.gaierror),
)
BAD_HOST_AUTH_FAILURE = JumpHost(
    "fakehost",
    connection_func=lambda host: mock_connect(paramiko.AuthenticationException),
    docker_client_func=Mock(side_effect=paramiko.AuthenticationException),
)

# START TESTS


@pytest.mark.parametrize(
    "jump_host",
    [BAD_HOST_AUTH_FAILURE, BAD_HOST_DNS_FAILURE, BAD_HOST_TIMEOUT],
)
def test_jump_host_connection_errors(jump_host):
    with pytest.raises(ConnectionError):
        jump_host.connect()

    with pytest.raises(ConnectionError):
        jump_host.docker_client()


def test_try_connect_to_any():
    # Good host first
    host, _ = JumpHost.try_connect_to_any(
        GOOD_HOST_ONE, GOOD_HOST_TWO, BAD_HOST_BAD_CODE, BAD_HOST_TIMEOUT
    )
    assert host is GOOD_HOST_ONE
    assert host is not GOOD_HOST_TWO

    # Check order is maintained and first successful host returned.
    host, _ = JumpHost.try_connect_to_any(
        GOOD_HOST_TWO, GOOD_HOST_ONE, BAD_HOST_BAD_CODE, BAD_HOST_TIMEOUT
    )
    assert host is GOOD_HOST_TWO
    assert host is not GOOD_HOST_ONE

    # Bad hosts first, should be passed over
    host, _ = JumpHost.try_connect_to_any(
        BAD_HOST_BAD_CODE, BAD_HOST_TIMEOUT, GOOD_HOST_TWO, GOOD_HOST_ONE
    )
    assert host is GOOD_HOST_TWO

    # Only bad hosts, raises last exception
    with pytest.raises(ZeroDivisionError):
        JumpHost.try_connect_to_any(BAD_HOST_TIMEOUT, BAD_HOST_BAD_CODE)

    with pytest.raises(ConnectionError):
        JumpHost.try_connect_to_any(BAD_HOST_BAD_CODE, BAD_HOST_TIMEOUT)


def test_choose_from_jump_hosts():
    # Check that with no override set we always pick the good host.
    for _ in range(10):
        chosen_host = JumpHost.choose_from(
            BAD_HOST_TIMEOUT, BAD_HOST_AUTH_FAILURE, GOOD_HOST_ONE
        )
        assert chosen_host is GOOD_HOST_ONE

    # Basic override by index
    chosen_host = JumpHost.choose_from(GOOD_HOST_ONE, GOOD_HOST_TWO, override=2)
    assert chosen_host is GOOD_HOST_TWO

    # Override does not check for failures
    chosen_host = JumpHost.choose_from(
        BAD_HOST_AUTH_FAILURE, GOOD_HOST_ONE, GOOD_HOST_TWO, override=1
    )
    assert chosen_host is BAD_HOST_AUTH_FAILURE

    # Override accepts string numeric index
    chosen_host = JumpHost.choose_from(
        BAD_HOST_AUTH_FAILURE, GOOD_HOST_ONE, GOOD_HOST_TWO, override="3"
    )
    assert chosen_host is GOOD_HOST_TWO

    # Allow arbitrary host override
    chosen_host = JumpHost.choose_from(GOOD_HOST_ONE, GOOD_HOST_TWO, override="my-host")
    assert chosen_host.host == "my-host"


# HELPER FUNCTIONS


def mock_connect(open_exception=None, *args, **kwargs):
    """
    Return a Mock for fabric.Connection, that throws an exception.

    The exception is thrown when open or run are called.
    """
    mock_connection = Mock(spec=fabric.Connection)
    if open_exception is not None:
        mock_connection.open.side_effect = open_exception
        mock_connection.run.side_effect = open_exception
    return mock_connection
