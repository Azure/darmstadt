import time

import pytest

from darmstadt.parallel import run_in_parallel


def test_run_in_parallel():
    def one_second_square_function(x):
        time.sleep(1)
        return x * x

    start_time = time.time()
    result = run_in_parallel([1, 2, 4, 5], one_second_square_function)
    end_time = time.time()
    assert end_time - start_time > 1
    assert end_time - start_time < 2
    assert result == {1: 1, 2: 4, 4: 16, 5: 25}


def test_run_in_parallel_with_exception():
    # By default we return exceptions
    result = run_in_parallel([1, 0, 2], lambda x: 2 / x)
    assert result[1] == 2
    assert result[2] == 1
    with pytest.raises(ZeroDivisionError):
        raise result[0]

    # We can choose to throw Exceptions immediately
    with pytest.raises(ZeroDivisionError):
        run_in_parallel([1, 0, 2], lambda x: 2 / x, return_exceptions=False)
