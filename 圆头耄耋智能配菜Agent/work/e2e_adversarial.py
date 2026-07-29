#!/usr/bin/env python3
import argparse
import socket
import sys
import unittest
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "backend"):
    resolved = str(import_root)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


DEFAULT_MODULES = [
    "backend.tests.test_fakes",
    "backend.tests.test_jobs_adversarial",
    "backend.tests.test_channel_swap_adversarial",
    "backend.tests.test_upstream_adversarial",
]


def _deny_network(event: str, _arguments) -> None:
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("network access is disabled in adversarial tests")


def _parse_arguments(arguments: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the offline backend adversarial acceptance suite."
    )
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Override the default suite with one or more unittest modules.",
    )
    return parser.parse_args(arguments)


def main(arguments: List[str]) -> int:
    options = _parse_arguments(arguments)
    modules = options.modules or DEFAULT_MODULES
    sys.addaudithook(_deny_network)

    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2,
    ).run(suite)
    if result.wasSuccessful():
        print("ADVERSARIAL PASS tests={}".format(result.testsRun))
        return 0

    print(
        "ADVERSARIAL FAIL tests={} failures={} errors={}".format(
            result.testsRun,
            len(result.failures),
            len(result.errors),
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
