import secrets
from io import BytesIO, StringIO

import pytest

from darmstadt.remote_controller import ContainerController


@pytest.fixture
def test_uid():
    return secrets.token_hex(8)


def test_container_controller(test_uid):
    container = ContainerController(f"mycsar-{test_uid}", "alpine")
    container.start()
    try:
        ls_result = container.run("echo 'Hello World'", in_stream=False)
        assert ls_result.stdout == "Hello World\n"
    finally:
        container.remove()


def test_nested_container_controller(test_uid):
    dind_container = ContainerController(f"dind-{test_uid}", "docker:dind")
    dind_container.start()
    dind_container.run(
        "sh -c 'while [ ! -e /var/run/docker.sock ]; do sleep 1; done'", in_stream=False
    )

    try:
        container = ContainerController(
            f"mycsar-{test_uid}", "alpine", jump_host=dind_container
        )
        container.start()
        ls_result = container.run("echo 'Hello World'", in_stream=False)
        assert ls_result.stdout == "Hello World\n"
    finally:
        dind_container.remove()


def test_container_put(tmp_path, test_uid):
    with open(tmp_path / "myfile", "w") as f:
        f.write("this is my file")

    container = ContainerController(f"mycsar-{test_uid}", "alpine")
    container.start()

    try:
        container.put(str(tmp_path / "myfile"), "/tmp/")
        assert (
            container.run("cat /tmp/myfile", in_stream=False).stdout
            == "this is my file"
        )

        container.put(str(tmp_path / "myfile"), "/tmp/rename")
        assert (
            container.run("cat /tmp/rename", in_stream=False).stdout
            == "this is my file"
        )

        container.put(str(tmp_path / "myfile"))
        assert container.run("cat myfile", in_stream=False).stdout == "this is my file"

        container.put(StringIO("this is stringio"), "textio")
        assert container.run("cat textio", in_stream=False).stdout == "this is stringio"

        container.put(StringIO("this is stringio"), "/tmp/tmptextio")
        assert (
            container.run("cat /tmp/tmptextio", in_stream=False).stdout
            == "this is stringio"
        )

        container.put(BytesIO(b"this is bytesio"), "binaryio")
        assert (
            container.run("cat binaryio", in_stream=False).stdout == "this is bytesio"
        )

        container.put(BytesIO(b"this is bytesio"), "/tmp/tmpbinaryio")
        assert (
            container.run("cat /tmp/tmpbinaryio", in_stream=False).stdout
            == "this is bytesio"
        )
    finally:
        container.remove()
