"""Run unittest; optional selector polling for socket-restricted test sandboxes."""

import argparse
import asyncio
import selectors
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class PollSelector(selectors.DefaultSelector):
    def select(self, timeout=None):
        # Some sandboxes allow socketpair creation but deny its wakeup writes.
        return super().select(0.02 if timeout is None else min(timeout, 0.02))


class PollPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return asyncio.SelectorEventLoop(PollSelector())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox-poll", action="store_true")
    args = parser.parse_args()
    if args.sandbox_poll:
        asyncio.set_event_loop_policy(PollPolicy())
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
