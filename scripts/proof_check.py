"""Trusted Proof Loop command-json adapter; runs checks against its snapshot."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path


def ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from ids(item)
        else:
            yield item.id()


def main():
    request = json.load(sys.stdin)
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    os.environ["PYTHONPATH"] = str(root)
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    with contextlib.redirect_stdout(sys.stderr):
        suite = unittest.defaultTestLoader.discover(str(root / "acceptance"), pattern=sys.argv[1])
        actual = list(ids(suite))
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    findings = []
    if actual != request["coverage"]:
        findings.append("Observed test identities differ from frozen coverage")
    if not result.wasSuccessful() or result.skipped or result.expectedFailures or result.unexpectedSuccesses or result.testsRun != len(actual):
        findings.append("Tests failed, skipped, or were not all executed")
    # Ensure editable installation cannot redirect direct imports out of snapshot.
    import cli_anything.ableton
    if not Path(cli_anything.ableton.__file__).resolve().is_relative_to(root):
        findings.append("Candidate import escaped the snapshot")
    response = {"schema_version": 1, "check_id": request["check_id"],
                "state": "fail" if findings else "pass", "findings": findings, "coverage": actual}
    print(json.dumps(response))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
