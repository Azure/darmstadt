"""Helper functions for running in parallel, e.g. across multiple hosts."""

import asyncio
from concurrent.futures import ThreadPoolExecutor


def run_in_parallel(operands, operator_func, return_exceptions=True):
    """
    Runs a function in parallel across a list of operands.

    >>> run_in_parallel([1, 2, 4, 5], lambda x: x * x)
    {1: 1, 2: 4, 4: 16, 5: 25}

    >>> run_in_parallel([1, 0, 2], lambda x: 2/x)
    {1: 2.0, 0: ZeroDivisionError('division by zero'), 2: 1.0}

    >>> run_in_parallel([1, 0, 2], lambda x: 2/x, return_exceptions=False)
    Traceback (most recent call last):
      ...
    ZeroDivisionError: division by zero
    """

    async def coroutine(op, loop, executor):
        try:
            result = await loop.run_in_executor(executor, lambda: operator_func(op))
        except Exception as e:  # pylint: disable=broad-except
            if return_exceptions:
                result = e
            else:
                raise e

        return op, result

    async def gather_results():
        with ThreadPoolExecutor(max_workers=len(operands)) as executor:
            loop = asyncio.get_event_loop()
            result = await asyncio.gather(
                *[coroutine(op, loop, executor) for op in operands],
            )
        return result

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(gather_results())
    return dict(results)
