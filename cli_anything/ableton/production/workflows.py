"""Explicit reference briefs, sample edits and comparable master versions."""
from typing import Literal
import json
from pydantic import Field
from . import audio
from .render import Strict, master
from .workspace import digest, timestamp, write_json
from .ledger import Ledger
from .progress import checkpoint

PROFILES = {
    "dynamic": {"target": -15.0, "ceiling": -1.0, "release_ms": 120.0, "lookahead_ms": 5.0, "reduction_budget_db": 3.0},
    "balanced": {"target": -12.0, "ceiling": -1.0, "release_ms": 80.0, "lookahead_ms": 5.0, "reduction_budget_db": 6.0},
    "dense": {"target": -9.0, "ceiling": -1.0, "release_ms": 50.0, "lookahead_ms": 3.0, "reduction_budget_db": 9.0},
}


class Section(Strict):
    path: str = Field(min_length=1, max_length=500)
    start_seconds: float = Field(default=0, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)


class ReferenceBrief(Strict):
    label: str = Field(min_length=1, max_length=100)
    reference: Section
    candidate: Section | None = None
    focus: list[Literal["bass", "tonal_balance", "width", "dynamics", "arrangement", "effects"]] = Field(min_length=1, max_length=6)
    user_notes: str = Field(default="", max_length=2000)


class SampleEdit(Section):
    reverse: bool = False
    fade_in_ms: float = Field(default=2, ge=0, le=5000)
    fade_out_ms: float = Field(default=5, ge=0, le=5000)
    gain_db: float = Field(default=0, ge=-24, le=12)
    peak_normalize_dbfs: float | None = Field(default=None, ge=-24, le=-0.1)
    note: str = Field(default="", max_length=1000)


class Variant(Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
    profile: Literal["dynamic", "balanced", "dense"]


class Experiment(Strict):
    path: str = Field(min_length=1, max_length=500)
    intent: str = Field(min_length=1, max_length=1000)
    versions: list[Variant] = Field(min_length=1, max_length=3)
    parent_event_id: str | None = Field(default=None, min_length=1, max_length=64)


def section(workspace, spec, min_seconds=.5):
    path = workspace.path(spec.path)
    x, sr = audio.load(path, min_seconds=min_seconds)
    end = len(x) / sr if spec.end_seconds is None else spec.end_seconds
    if end > len(x) / sr or spec.start_seconds >= end:
        raise ValueError("Section must lie inside the source and end after its start")
    start_frame, end_frame = round(spec.start_seconds * sr), round(end * sr)
    if end_frame - start_frame < round(min_seconds * sr):
        raise ValueError(f"Section must be at least {min_seconds} seconds")
    return x[start_frame:end_frame].copy(), sr, {"path": spec.path, "source_sha256": digest(path),
        "start_frame": start_frame, "end_frame": end_frame, "sample_rate": sr}


def reference_brief(workspace, raw):
    spec = ReferenceBrief.model_validate(raw)
    x, sr, provenance = section(workspace, spec.reference)
    checkpoint("analyze","Measuring the reference passage")
    reference = audio.analyze_array(x, sr)
    comparison = None
    candidate_provenance = None
    if spec.candidate:
        checkpoint("analyze","Measuring the candidate passage")
        y, yr, candidate_provenance = section(workspace, spec.candidate)
        candidate = audio.analyze_array(y, yr)
        # Match bands by bounds, never by list position across different rates.
        bands = {tuple(b["hz"]): b["rms_dbfs"] - reference["integrated_lufs"] for b in reference["spectrum"]}
        comparison = {"candidate": candidate, "candidate_level_match_db": reference["integrated_lufs"] - candidate["integrated_lufs"],
            "spectral_delta_db": [{"hz": b["hz"], "delta": b["rms_dbfs"] - candidate["integrated_lufs"] - bands[tuple(b["hz"]) ]}
                                  for b in candidate["spectrum"] if tuple(b["hz"]) in bands],
            "crest_delta_db": candidate["crest_db"] - reference["crest_db"],
            "mono_loss_delta_db": candidate["mono_fold_loss_db"] - reference["mono_fold_loss_db"]}
    report = {"kind":"reference_brief", "created":timestamp(), "label":spec.label, "focus":spec.focus,
        "user_notes":spec.user_notes, "reference_source":provenance, "candidate_source":candidate_provenance,
        "reference_metrics":reference, "comparison":comparison,
        "boundary":"Measurements describe the selected mixed audio. No stem/gear inference, EQ cloning, artist imitation or perceptual similarity score. Arrangement/effects focus requires human interpretation.",
        "speaker_playback":False, "creative_acceptance":"pending"}
    checkpoint("write")
    output = workspace.new_render()
    write_json(output / "reference-brief.json", report)
    checkpoint("record")
    event = Ledger(workspace).append("review", ["reference", *spec.focus], report)
    return {"event_id":event, "output_directory":workspace.relative(output), **report}


def edit_sample(workspace, raw):
    np, sf, _, _ = audio.dependencies()
    spec = SampleEdit.model_validate(raw)
    x, sr, provenance = section(workspace, spec, min_seconds=.01)
    # Finite FLOAT inputs may still be far above normal audio levels.
    x = x.astype(np.float64)
    fade_in, fade_out = round(spec.fade_in_ms * sr / 1000), round(spec.fade_out_ms * sr / 1000)
    if fade_in + fade_out > len(x):
        raise ValueError("Combined fades must fit inside the edited section")
    checkpoint("edit")
    if spec.reverse:
        x = x[::-1].copy()
    if fade_in:
        x[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    if fade_out:
        x[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
        x[-1] = 0
    x *= 10 ** (spec.gain_db / 20)
    peak = float(np.max(np.abs(x)))
    if peak < 1e-7:
        raise ValueError("Edited sample is silent")
    if spec.peak_normalize_dbfs is not None:
        x *= 10 ** (spec.peak_normalize_dbfs / 20) / peak
    if not np.isfinite(x).all() or float(np.max(np.abs(x))) < 1e-7:
        raise ValueError("Edited sample is nonfinite or silent after processing")
    if float(np.max(np.abs(x))) >= 1:
        raise ValueError("Sample edit would clip; reduce gain or explicitly set peak_normalize_dbfs")
    checkpoint("write")
    output = workspace.new_render()
    target = output / "sample.wav"
    sf.write(target, x, sr, subtype="PCM_24")
    report = {"kind":"sample_edit", "source":provenance, "edit":spec.model_dump(),
        "output_path":workspace.relative(target), "sha256":digest(target), "frames":len(x),
        "duration_seconds":len(x) / sr, "sample_peak_dbfs":audio.db(np.max(np.abs(x))),
        "speaker_playback":False, "perceptual_listening":False,
        "boundary":"File trim/reverse/fades/gain only. Native warping, pitch shifting and slicing-to-MIDI are separate methods."}
    checkpoint("record")
    write_json(output / "sample-edit.json", report)
    event = Ledger(workspace).append("render", ["sample-edit"], report)
    return {"event_id":event, **report}


def master_versions(workspace, raw):
    np, sf, _, _ = audio.dependencies()
    spec = Experiment.model_validate(raw)
    filenames = [name.casefold() for v in spec.versions for name in (v.name + ".wav", v.name + "-level-matched.wav")]
    if len(set(filenames)) != len(filenames):
        raise ValueError("Version and comparison filenames must be unique, including case")
    source = workspace.path(spec.path)
    source_hash = digest(source)
    ledger = Ledger(workspace)
    if spec.parent_event_id:
        with ledger.connect() as db:
            row = db.execute("SELECT kind,payload FROM events WHERE id=?", (spec.parent_event_id,)).fetchone()
        if row is None or row[0] != "render":
            raise ValueError("Parent must identify an existing render event")
        parent = json.loads(row[1])
        # A declared relationship alone does not establish derivation.
        hashes = [parent.get("sha256"), parent.get("master", {}).get("sha256")]
        hashes += [v.get("metrics", {}).get("sha256") for v in parent.get("versions", [])]
        hashes += [v.get("comparison_sha256") for v in parent.get("versions", [])]
        if source_hash not in hashes:
            raise ValueError("Source hash does not identify an output of the parent render")
    x, sr = audio.load(source)
    checkpoint("versions","Rendering named versions",0,len(spec.versions))
    output = workspace.new_render()
    reports = []
    for version in spec.versions:
        settings = PROFILES[version.profile].copy()
        y, decisions = master(x, sr, max_attempts=2, **settings)
        target = output / (version.name + ".wav")
        sf.write(target, y, sr, subtype="PCM_24")
        reports.append({"name":version.name, "profile":version.profile, "settings":settings,
                        "path":workspace.relative(target), "decisions":decisions, "metrics":audio.analyze(target)})
        checkpoint("versions","Rendering and measuring versions",len(reports),len(spec.versions))
    shared_lufs = min(v["metrics"]["integrated_lufs"] for v in reports)
    checkpoint("comparisons","Writing attenuated comparisons",0,len(reports))
    for index, report in enumerate(reports):
        y, _ = audio.load(workspace.path(report["path"]))
        attenuation = min(0, shared_lufs - report["metrics"]["integrated_lufs"])
        y *= 10 ** (attenuation / 20)
        target = output / (report["name"] + "-level-matched.wav")
        sf.write(target, y, sr, subtype="PCM_24")
        report["comparison_path"] = workspace.relative(target)
        report["comparison_sha256"] = digest(target)
        report["comparison_attenuation_db"] = attenuation
        report["comparison_lufs"] = audio.loudness(y, sr)
        checkpoint("comparisons","Writing attenuated comparisons",index+1,len(reports))
    report = {"kind":"master_versions", "created":timestamp(), "source_path":spec.path,
        "source_sha256":source_hash, "source_preserved":digest(source) == source_hash,
        "parent_event_id":spec.parent_event_id, "intent":spec.intent, "versions":reports,
        "shared_comparison_lufs":shared_lufs, "output_directory":workspace.relative(output),
        "creative_winner":None, "creative_acceptance":"pending", "speaker_playback":False,
        "boundary":"Authored loudness/timing profiles using this tool's linked limiter, not vendor algorithms or genre standards. Level-matched files support later human comparison."}
    checkpoint("record")
    write_json(output / "versions.json", report)
    event = ledger.append("render", ["master-versions"], report)
    return {"event_id":event, **report}
