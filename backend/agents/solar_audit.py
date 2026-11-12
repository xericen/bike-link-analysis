"""Credential-free per-call accounting. Never infer billing for lost responses."""
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

AUDIT_DIR = Path(__file__).resolve().parents[2] / "data" / "solar-audit"
TOKEN_KEYS = ("prompt_tokens","completion_tokens","total_tokens")

class CallAudit:
    def __init__(self, model):
        self.request_id = uuid4().hex
        self.model = model
        self.calls = []

    def _write(self, event):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = AUDIT_DIR / (datetime.now(timezone.utc).strftime("%Y-%m-%d")+".jsonl")
        record = {"timestamp":datetime.now(timezone.utc).isoformat(),"request_id":self.request_id,
                  "requested_model":self.model,**event}
        fd = os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
        with os.fdopen(fd,"a",encoding="utf-8") as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            stream.write(json.dumps(record,ensure_ascii=False)+"\n")
            stream.flush()
            fcntl.flock(stream,fcntl.LOCK_UN)

    def complete(self, client, stage, **kwargs):
        entry = {"stage":stage,"state":"pending","usage":None}
        self.calls.append(entry)
        self._write({"call_number":len(self.calls),**entry})
        try:
            raw = client.chat.completions.with_raw_response.create(model=self.model,**kwargs)
            completion = raw.parse()
            entry.update({"state":"completed","http_status":raw.status_code,
                "response_id":completion.id,"model":completion.model,
                "finish_reason":completion.choices[0].finish_reason if completion.choices else None,
                "usage":{key:getattr(completion.usage,key,0) or 0 for key in TOKEN_KEYS} if completion.usage else None})
            self._write({"call_number":len(self.calls),**entry})
            return completion
        except Exception as exc:
            entry.update({"state":"failed","error_type":type(exc).__name__,
                          "http_status":getattr(exc,"status_code",None)})
            self._write({"call_number":len(self.calls),**entry})
            raise

    def summary(self):
        return {"request_id":self.request_id,"provider_calls":self.calls,
                "usage":{key:sum((call.get("usage") or {}).get(key,0) for call in self.calls) for key in TOKEN_KEYS},
                "usage_complete":bool(self.calls) and all(call.get("usage") is not None for call in self.calls),
                "billing_status":"provider_usage_reported" if self.calls and all(call.get("usage") is not None for call in self.calls) else "unknown_for_unreported_calls"}
