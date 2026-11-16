"""Content-addressed input versions, verified offline; requests only check local receipts."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):h.update(block)
    return h.hexdigest()
def inputs(folder):
    folder=Path(folder)
    files=[p for p in folder.iterdir() if p.is_file() and
           (p.suffix in {".csv",".json"} or p.name=="analysis.sqlite") and
           p.name not in {"kpi_inputs.json","kpi_verified.json"}]
    files+=list((ROOT/"backend/analysis").glob("*.py"))+list((ROOT/"backend/services").glob("*.py"))
    return sorted(files)
def key(path,folder):
    return "data/"+path.name if path.parent==Path(folder) else str(path.relative_to(ROOT))
def inventory(folder):
    return [{"path":key(p,folder),"sha256":digest(p),"size":p.stat().st_size} for p in inputs(folder)]
def atomic(path,value):
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True));os.replace(temp,path)
def verify(folder,create=False):
    folder=Path(folder);file=folder/"kpi_inputs.json"
    entries=inventory(folder)
    revision=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
    if not create:
        manifest=json.loads(file.read_text())
        if manifest["revision"]!=revision or manifest["files"]!=entries:
            raise RuntimeError("Input content differs from manifest; rebuild aggregates before release")
    else:
        manifest={"schema":1,"revision":revision,"files":entries}
        atomic(file,manifest)
    receipt={"manifest_sha256":digest(file),"files":[[key(p,folder),p.stat().st_size,p.stat().st_mtime_ns] for p in inputs(folder)]}
    atomic(folder/"kpi_verified.json",receipt)
    return revision
def current(folder):
    folder=Path(folder);file=folder/"kpi_inputs.json"
    if not file.exists():
        # Fixtures may use their own isolated inputs. Production must be prepared offline.
        if folder==ROOT/"data/processed":return "unverified-inputs"
        return hashlib.sha256(json.dumps(inventory(folder),sort_keys=True).encode()).hexdigest()
    try:
        manifest=json.loads(file.read_text());receipt=json.loads((folder/"kpi_verified.json").read_text())
        if receipt["manifest_sha256"]!=digest(file):return "unverified-inputs"
        stats=[[key(p,folder),p.stat().st_size,p.stat().st_mtime_ns] for p in inputs(folder)]
        return manifest["revision"] if receipt["files"]==stats else "unverified-inputs"
    except (OSError,ValueError,KeyError):return "unverified-inputs"
