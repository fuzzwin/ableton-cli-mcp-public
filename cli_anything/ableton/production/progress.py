"""Observed per-job stages; local files and optional client notifications."""
import copy
import json
import math
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from .workspace import timestamp

CURRENT = ContextVar("ableton_production_job", default=None)
OBSERVER = ContextVar("ableton_production_observer", default=None)
PLANS = {
    "analysis":[("preflight","Checking inputs"),("analyze","Reading and analyzing audio"),("record","Recording evidence")],
    "mix":[("preflight","Checking inputs"),("mix","Mixing stems"),("master","Mastering bounce"),("write","Writing new files"),("checks","Checking saved bounce"),("record","Recording evidence")],
    "master":[("preflight","Checking inputs"),("master","Mastering bounce"),("write","Writing new file"),("checks","Checking saved bounce"),("record","Recording evidence")],
    "sample_edit":[("preflight","Checking inputs"),("edit","Editing sample"),("write","Writing new sample"),("record","Recording evidence")],
    "reference":[("preflight","Checking inputs"),("analyze","Measuring selected passages"),("write","Writing reference brief"),("record","Recording evidence")],
    "master_versions":[("preflight","Checking inputs"),("versions","Rendering and checking versions"),("comparisons","Writing matched comparisons"),("record","Recording version history")],
    "inventory":[("preflight","Checking request"),("inventory","Reading plugin context")],
    "probe":[("preflight","Checking selected plugin"),("render","Rendering test file"),("record","Recording plugin outcome")],
}


@contextmanager
def observe(callback):
    token = OBSERVER.set(callback)
    try:
        yield
    finally:
        OBSERVER.reset(token)


def checkpoint(stage, detail="", completed=None, total=None):
    job = CURRENT.get()
    if job is not None:
        job.advance(stage, detail, completed, total)


class Job:
    def __init__(self, workspace, operation, heartbeat_seconds=5):
        if operation not in PLANS:
            raise ValueError("Unknown progress operation")
        self.workspace = workspace
        workspace.state_dir()
        directory = workspace.path(".ableton-harness/jobs", exists=False)
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.id = uuid.uuid4().hex
        self.path = directory / (self.id + ".json")
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.observer = OBSERVER.get()
        self.interval = heartbeat_seconds
        self.started = time.monotonic()
        self.data = {"schema_version":1,"job_id":self.id,"operation":operation,"state":"running",
            "started":timestamp(),"updated":timestamp(),"heartbeat_epoch":time.time(),"elapsed_seconds":0,
            "current_stage":None,"detail":"","completed_stages":0,"total_stages":len(PLANS[operation]),
            "stages":[{"id":id,"label":label,"state":"queued"} for id,label in PLANS[operation]],
            "events":[],"sequence":0,"speaker_playback":False,"creative_acceptance":"pending","observer_errors":0}

    def persist(self, event=None):
        # Caller holds lock. Unique temp prevents overlapping heartbeats/stages.
        self.data.update(updated=timestamp(),heartbeat_epoch=time.time(),elapsed_seconds=time.monotonic()-self.started)
        if event:
            self.data["sequence"]+=1
            self.data["events"].append({"time":timestamp(),"text":event.encode()[:300].decode(errors="ignore")})
            if len(self.data["events"]) > 128:
                self.data["events"]=self.data["events"][-128:]
                self.data["history_truncated"]=True
        temp=self.path.with_suffix("."+uuid.uuid4().hex+".tmp")
        with temp.open("x",encoding="utf-8") as f:
            json.dump(self.data,f,allow_nan=False,separators=(",",":"))
        os.replace(temp,self.path)
        return copy.deepcopy(self.data)

    def notify(self, snapshot):
        if self.observer:
            try:
                self.observer(snapshot)
            except Exception:
                # Notification transport is not the audio operation's outcome.
                with self.lock:
                    self.data["observer_errors"]+=1

    def __enter__(self):
        self.token=CURRENT.set(self)
        try:
            with self.lock:
                snapshot=self.persist("Started "+self.data["operation"])
            self.notify(snapshot)
            self.thread=threading.Thread(target=self.heartbeat,daemon=True)
            self.thread.start()
            self.advance(PLANS[self.data["operation"]][0][0])
            return self
        except BaseException:
            self.stop.set()
            if hasattr(self,"thread"):self.thread.join(timeout=1)
            CURRENT.reset(self.token)
            raise

    def heartbeat(self):
        while not self.stop.wait(self.interval):
            try:
                with self.lock:
                    if self.data["state"] != "running":
                        return
                    self.persist()  # Liveness only; no invented work event.
            except OSError:
                return  # Reader will mark old heartbeat unconfirmed.

    def advance(self, stage, detail="", completed=None, total=None):
        if len(detail)>300 or (completed is None) != (total is None):
            raise ValueError("Invalid progress detail/counts")
        if completed is not None and (type(completed) is not int or type(total) is not int or not 0<=completed<=total or total<=0):
            raise ValueError("Invalid progress item counts")
        with self.lock:
            if self.data["state"]!="running":
                raise ValueError("Cannot advance a terminal job")
            stages=self.data["stages"]
            index=next((i for i,s in enumerate(stages) if s["id"]==stage),None)
            current=self.data["current_stage"]
            old=next((i for i,s in enumerate(stages) if s["id"]==current),-1)
            if index is None or index<old or index>old+1:
                raise ValueError("Progress stages must follow observed order")
            if index!=old and old>=0:
                stages[old]["state"]="complete"
            stages[index]["state"]="running"
            self.data.update(current_stage=stage,detail=detail,completed_stages=sum(s["state"]=="complete" for s in stages))
            self.data["items"]={"completed":completed,"total":total} if completed is not None else None
            event=stages[index]["label"]+(": "+detail if detail else "")
            if completed is not None:event+=f" ({completed}/{total})"
            snapshot=self.persist(event)
        self.notify(snapshot)

    def outcome(self, result):
        self.data["result"]={k:result[k] for k in ("event_id","output_directory","output_path","status","technical_pass") if k in result}
        warning=(result.get("technical_pass") is False or result.get("source_preserved") is False
                 or result.get("source_files_preserved") is False
                 or result.get("status") in {"load_error","timeout","silent_or_invalid"})
        decisions=[result["mastering"]] if "mastering" in result else [v["decisions"] for v in result.get("versions",[])]
        for decision in decisions:
            chosen=decision["candidates"][decision["selected_attempt"]-1]
            warning=warning or not chosen.get("loudness_target_met",True) or not chosen.get("reduction_budget_met",True)
        self.attention=bool(warning)

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        self.thread.join(timeout=1)
        try:
            with self.lock:
                current=next((s for s in self.data["stages"] if s["id"]==self.data["current_stage"]),None)
                if exc is not None:
                    if current:current["state"]="failed"
                    self.data.update(state="failed",error=str(exc)[:1000])
                else:
                    if current:current["state"]="complete"
                    queued=any(s["state"]=="queued" for s in self.data["stages"])
                    self.data["state"]="unconfirmed" if queued else ("needs_attention" if getattr(self,"attention",False) else "completed")
                    if queued:self.data["error"]="Operation returned before every declared stage was observed"
                self.data["completed_stages"]=sum(s["state"]=="complete" for s in self.data["stages"])
                snapshot=self.persist("Operation "+self.data["state"])
            self.notify(snapshot)
        finally:
            CURRENT.reset(self.token)
        return False


def read_jobs(workspace, job_id=None, limit=8, now=None):
    if job_id is not None and not re.fullmatch(r"[0-9a-f]{32}",job_id):
        raise ValueError("Invalid job ID")
    if type(limit) is not int or not 1<=limit<=20:
        raise ValueError("Job limit must be 1..20")
    directory=workspace.path(".ableton-harness/jobs",exists=False)
    if not directory.exists():
        return {"jobs":[],"limit_note":"No recorded production jobs yet"}
    paths=[directory/(job_id+".json")] if job_id else sorted(directory.glob("*.json"),key=lambda p:p.lstat().st_mtime,reverse=True)[:limit]
    results=[]
    for path in paths:
        if not path.exists():continue
        if path.is_symlink() or not path.resolve().is_relative_to(workspace.root) or path.stat().st_size>128*1024:
            raise ValueError("Unsafe or oversized job record")
        try:
            data=json.loads(path.read_text(),parse_constant=invalid_number,parse_float=finite_number)
            validate_record(data,path.stem)
            observed_now=time.time() if now is None else now
            age=max(0,observed_now-data["heartbeat_epoch"])
            data["heartbeat_age_seconds"]=age
            if data["state"]=="running" and age>20:
                data.update(state="unconfirmed",liveness_note="No heartbeat within 20 seconds; completion is unknown")
            if data["state"]=="running" and data["heartbeat_epoch"]>observed_now+5:
                data.update(state="unconfirmed",liveness_note="Heartbeat timestamp is in the future; liveness is unconfirmed")
            results.append(data)
        except (OSError,ValueError,KeyError,TypeError):
            results.append({"job_id":path.stem,"state":"unconfirmed","error":"Job record unavailable or invalid"})
    return {"jobs":results,"limit_note":"Observed stages and item counts, not time percentages or ETA. No playback/cancellation controls."}


def invalid_number(value):
    raise ValueError("Nonfinite job number")


def finite_number(value):
    number=float(value)
    if not math.isfinite(number):raise ValueError("Nonfinite job number")
    return number


def validate_record(data,identity):
    """Reject corrupt snapshots before they can claim liveness or success."""
    def require(condition):
        if not condition:raise ValueError("Invalid job record")
    require(isinstance(data,dict))
    require(bool(re.fullmatch(r"[0-9a-f]{32}",identity)))
    require(type(data.get("schema_version")) is int and data["schema_version"]==1 and data.get("job_id")==identity)
    operation=data.get("operation")
    require(isinstance(operation,str) and operation in PLANS)
    state=data.get("state")
    require(isinstance(state,str) and state in {"running","completed","needs_attention","failed","unconfirmed"})
    for name in ("heartbeat_epoch","elapsed_seconds"):
        value=data.get(name)
        require(type(value) in (int,float) and math.isfinite(value) and value>=0)
    for name in ("started","updated"):
        require(isinstance(data.get(name),str) and len(data[name])<=80)
        from datetime import datetime
        require(datetime.fromisoformat(data[name]).tzinfo is not None)
    stages=data.get("stages")
    require(isinstance(stages,list) and len(stages)==len(PLANS[operation]))
    for stage,(name,label) in zip(stages,PLANS[operation]):
        require(isinstance(stage,dict) and stage.get("id")==name and stage.get("label")==label)
        require(stage.get("state") in {"queued","running","complete","failed"})
    require(type(data.get("total_stages")) is int and data["total_stages"]==len(stages))
    require(type(data.get("completed_stages")) is int and data["completed_stages"]==sum(s["state"]=="complete" for s in stages))
    require(data.get("current_stage") is None or data["current_stage"] in {s["id"] for s in stages})
    require(sum(s["state"] in {"running","failed"} for s in stages)<=1)
    require("current_stage" in data)
    current=next((i for i,s in enumerate(stages) if s["id"]==data["current_stage"]),None)
    if state=="running":
        if current is None:require(all(s["state"]=="queued" for s in stages))
        else:
            require(stages[current]["state"]=="running")
            require(all(s["state"]=="complete" for s in stages[:current]))
            require(all(s["state"]=="queued" for s in stages[current+1:]))
    if state in {"completed","needs_attention"}:
        require(current==len(stages)-1 and all(s["state"]=="complete" for s in stages))
    if state=="failed":
        require(current is not None and stages[current]["state"]=="failed")
        require(all(s["state"]=="complete" for s in stages[:current]))
        require(all(s["state"]=="queued" for s in stages[current+1:]))
    require(type(data.get("sequence")) is int and data["sequence"]>=0)
    require(isinstance(data.get("detail"),str) and len(data["detail"])<=300)
    events=data.get("events")
    require(isinstance(events,list) and len(events)<=128)
    require(data["sequence"]>=len(events))
    require(all(isinstance(e,dict) and isinstance(e.get("text"),str) and isinstance(e.get("time"),str) for e in events))
    items=data.get("items")
    if items is not None:
        require(isinstance(items,dict) and type(items.get("completed")) is int and type(items.get("total")) is int)
        require(0<=items["completed"]<=items["total"] and items["total"]>0)
    require(data.get("speaker_playback") is False and data.get("creative_acceptance")=="pending")
