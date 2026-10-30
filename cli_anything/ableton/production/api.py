"""Common CLI/MCP facade. File operations stay in an explicit workspace."""
from .workspace import Workspace
from . import audio, plugins, knowledge
from .ledger import Ledger
from .progress import Job, checkpoint, read_jobs


class Production:
    def __init__(self, root):
        self.workspace = Workspace(root)

    def run(self, operation, work):
        with Job(self.workspace,operation) as job:
            result=work()
            job.outcome(result)
        return {**result,"progress_job_id":job.id}

    def analyze(self, path, reference=None):
        def work():
            source = self.workspace.path(path)
            checkpoint("analyze")
            result = audio.compare(source, self.workspace.path(reference)) if reference else audio.analyze(source)
            checkpoint("record")
            event_id = Ledger(self.workspace).append("analysis", ["analysis"], result)
            return {"event_id": event_id, **result}
        return self.run("analysis",work)

    def mix(self, plan_path):
        from .render import render_mix
        return self.run("mix",lambda:render_mix(self.workspace, self.workspace.read_json(plan_path)))

    def master(self, path, target_lufs=-12.0, ceiling_dbtp=-1.0):
        from .render import render_master
        return self.run("master",lambda:render_master(self.workspace, path, target_lufs, ceiling_dbtp))

    def inventory(self, query="", refresh=False, offset=0, limit=32):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 128 or len(query) > 200:
            raise ValueError("Inventory offset >=0, limit 1..128, query at most 200 characters")
        def work():
            checkpoint("inventory", "Refreshing metadata" if refresh else "Reading available inventory")
            data = plugins.inventory(self.workspace, refresh)
            items = [p for p in data["plugins"] if query.lower() in (str(p["name"]) + " " + p["format"]).lower()]
            return {"scanned": data["scanned"], "total": len(items), "items": items[offset:offset + limit],
                    "offset": offset, "host_architecture": data["host_architecture"], "limit_note": data["limit"]}
        return self.run("inventory",work)

    def probe(self, plugin_id):
        return self.run("probe",lambda:plugins.probe(self.workspace, plugin_id))

    def feedback(self, event_id, verdict, note, tags=None):
        return {"feedback_id": Ledger(self.workspace).feedback(event_id, verdict, note, tags or [])}

    def recall(self, query="", limit=20):
        return Ledger(self.workspace).recall(query, limit)

    def knowledge(self, query, limit=8, include_artist_examples=False):
        return knowledge.search(query, limit, include_artist_examples)

    def methods(self, query="", limit=8):
        return knowledge.methods(query, limit)

    def reference(self, plan_path):
        from .workflows import reference_brief
        return self.run("reference",lambda:reference_brief(self.workspace, self.workspace.read_json(plan_path)))

    def sample_edit(self, plan_path):
        from .workflows import edit_sample
        return self.run("sample_edit",lambda:edit_sample(self.workspace, self.workspace.read_json(plan_path)))

    def master_versions(self, plan_path):
        from .workflows import master_versions
        return self.run("master_versions",lambda:master_versions(self.workspace, self.workspace.read_json(plan_path)))

    def progress(self, job_id=None, limit=8):
        return read_jobs(self.workspace,job_id,limit)

    def plugin_context(self,query,goal="",refresh=False,limit=8):
        from .sound_design import context
        return context(self.workspace,query,goal,refresh,limit)

    def sound_design(self,plan_path):
        from .sound_design import render
        return self.run("sound_design",lambda:render(self.workspace,plan_path))
