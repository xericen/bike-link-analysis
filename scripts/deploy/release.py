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
    parser.add_argument("--check-url",help="FastAPI origin to smoke-test after deployment")
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
    if not args.verify_only:
        for module in ("scripts.validate.anchor_presentation_audit", "scripts.validate.decision_inputs",
                       "scripts.collect.audit_candidate_routes", "scripts.validate.decision_evidence"):
            subprocess.run([sys.executable, "-m", module], cwd=ROOT, env=env, check=True)
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
    from backend.presentation.monthly_trends import read as monthly_read
    monthly_months={}
    for city,expected in (("seoul",1954344),("daejeon",368491),("sejong",164366)):
        monthly=monthly_read(city,2025)
        december=next((row for row in monthly.get("months",[]) if row["month"]=="2025-12"),{})
        if not monthly.get("available") or len(monthly.get("months",[]))!=12 or december.get("rental_count")!=expected:
            raise RuntimeError("Missing or inconsistent monthly history artifact: "+city)
        monthly_months[city]=len(monthly["months"])
    for city in ("all","seoul","daejeon","sejong"):
        for folder in (ROOT/"frontend/public/assets/bike-link/usage",):
            asset=folder/(city+".json")
            if not asset.exists() or json.loads(asset.read_text())["views"]["all"]!=monthly_read(city):
                raise RuntimeError("Missing or outdated usage asset: "+str(asset))
    from backend.presentation import individual
    full_scopes=individual.scopes()
    if not full_scopes.get("ready"):raise RuntimeError("Missing individual full-history manifest")
    full_ready={}
    for city in ("seoul","daejeon","sejong"):
        scope=individual.scope(city)
        overview=individual.read(city,"overview")
        history=monthly_read(city)
        if overview["total_rentals"]!=history["summary"]["rental_count"]:raise RuntimeError("Individual total mismatch: "+city)
        for action in scope["actions"]:
            packet=individual.packet(city,action)
            if (packet["period_start"],packet["period_end"],packet["precomputed"]["revision"])!=(scope["start"],scope["end"],scope["revision"]):
                raise RuntimeError("Individual scope mismatch: "+city+"/"+action)
            a=individual.folder(city)/(action+".json")
            b=ROOT/"frontend/public/assets/bike-link/individual"/scope["asset_path"]/(action+".json")
            if a.read_bytes()!=b.read_bytes():raise RuntimeError("Different individual release copies")
        full_ready[city]={"start":scope["start"],"end":scope["end"],"actions":len(scope["actions"])}
    print(json.dumps({"individual":full_ready,"ready": True, "combinations": len(combos), "entries": count, "monthly_2025_months":monthly_months}), flush=True)
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if command:
        subprocess.run(command, cwd=ROOT.parent, env=env, check=True)
    if args.check_url:
        import requests
        response=requests.get(args.check_url.rstrip("/")+"/api/readiness",timeout=20)
        response.raise_for_status()
        body=response.json()
        if not body.get("ready"):
            raise RuntimeError("Deployed aggregate readiness failed")

if __name__ == "__main__":
    main()
