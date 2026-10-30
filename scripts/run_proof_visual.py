"""Execute the real pinned Proof Loop CLI and retain a live read-only view."""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / ".runtime/visual.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(data):
    VIEW.parent.mkdir(exist_ok=True)
    tmp = VIEW.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False))
    os.replace(tmp, VIEW)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof-loop", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task", default="task.json")
    args = parser.parse_args()
    data = {"run_id": args.run_id, "phase": "running", "started": now(),
            "silent": True, "events": [], "checks": [], "acceptance": "not_accepted"}
    contract = json.loads((ROOT / args.task).read_text())
    data["input_manifest"] = {relative: {"sha256": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                                        "mode": (ROOT / relative).stat().st_mode & 0o777}
                              for relative in [args.task] + contract["files"]}
    save(data)
    for command in ("harness-check", "harness-status"):
        argv = [sys.executable, "-B", str(args.proof_loop), command, "--root", str(ROOT),
                "--run-id", args.run_id, "--task", args.task]
        data["events"].append({"time": now(), "text": "Started " + command})
        save(data)
        try:
            proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=350)
            report = json.loads(proc.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            data.update(phase="error", error=str(exc), updated=now())
            save(data)
            return 2
        (ROOT / "docs" / (args.run_id + "-" + command + ".json")).write_text(json.dumps(report, indent=2))
        (ROOT / "docs" / (args.run_id + "-" + command + ".stderr")).write_text(proc.stderr)
        data[command] = report
        if command == "harness-status" and report.get("freshness", {}).get("state") != "current":
            data.update(verification=None, validation=None)
        data["events"].append({"time": now(), "text": command + " exited " + str(proc.returncode)})
        if command == "harness-check":
            data["checks"] = [{"id": c["id"], "state": c["state"], "criterion": c["criterion"],
                               "cases": len(c.get("observations", {}).get("coverage", [])),
                               "findings": c.get("observations", {}).get("findings", [])}
                              for c in report.get("checks", [])]
            data.update(candidate=report.get("candidate_sha256"),
                        verification=report.get("verification"), validation=report.get("validation"),
                        acceptance=report.get("acceptance", "not_accepted"))
        save(data)
        if proc.returncode:
            data.update(phase="needs attention", updated=now())
            save(data)
            return proc.returncode
    data.update(phase="checks complete", updated=now())
    save(data)
    print(json.dumps({"run_id": args.run_id, "phase": data["phase"], "checks": data["checks"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
