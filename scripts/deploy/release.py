"""Required deployment entrypoint: compute and verify before running a release command."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--verify-only",action="store_true",help="Verify copied manifests and cache without rebuilding")
    parser.add_argument("--check-url", help="FastAPI origin to smoke-test after deployment")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="Optional deployment command after --, run only after verification")
    args = parser.parse_args()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    report = ROOT / "docs/transit/deployment-precompute.json"
    sys.path.insert(0, str(ROOT))
    from backend.services.input_manifest import verify as verify_inputs
    if args.verify_only:
        verify_inputs(ROOT/"data/processed")
    else:
        subprocess.run([sys.executable, "scripts/preprocess/precompute_city_kpis.py",
                        "--report", str(report)], cwd=ROOT, env=env, check=True)
    sys.path.insert(0, str(ROOT))
    from scripts.preprocess.precompute_city_kpis import combinations
    from backend.services.deployment import verify
    combos = combinations()
    required = {"seoul", "daejeon", "sejong"}
    if not required.issubset({row[0] for row in combos}):
        raise RuntimeError("Missing required city data; release stopped")
    count = verify(combos)
    from backend.services.decision_evidence import read as decision_read
    decision_read("all")  # Release must include the matching offline decision study, too.
    print(json.dumps({"ready": True, "combinations": len(combos), "entries": count}), flush=True)
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if command:
        subprocess.run(command, cwd=ROOT.parent, env=env, check=True)
    if args.check_url:
        import requests
        response = requests.get(args.check_url.rstrip("/") + "/api/readiness", timeout=20)
        response.raise_for_status()
        body = response.json()
        if not body.get("ready"):
            raise RuntimeError("Deployed aggregate readiness failed")

if __name__ == "__main__":
    main()
