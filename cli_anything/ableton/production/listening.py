"""Silent, bounded evidence packets for reviewing bounced music.

This is signal analysis, not a perceptual audio model or an artistic judge.
"""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import audio
from .ledger import Ledger
from .progress import checkpoint
from .workspace import digest, write_json


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Section(Strict):
    name: str = Field(min_length=1, max_length=80)
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class Stem(Strict):
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=500)
    role: Literal["lead", "bass", "kick", "snare", "other"]
    monophonic: bool = False

    @model_validator(mode="after")
    def pitched_role(self):
        if self.monophonic and self.role not in {"lead", "bass"}:
            raise ValueError("Only an explicitly monophonic lead/bass supports pitch review")
        return self


class Plan(Strict):
    source: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, min_length=1, max_length=500)
    bpm: float | None = Field(default=None, ge=40, le=240)
    sections: list[Section] = Field(default_factory=list, max_length=24)
    stems: list[Stem] = Field(default_factory=list, max_length=4)
    focus: list[Literal["balance", "dynamics", "rhythm", "melody", "space", "arrangement"]] = Field(
        default_factory=lambda: ["balance", "dynamics", "rhythm", "melody", "space", "arrangement"], max_length=6)


def reduced(x, sr):
    np, _, _, signal = audio.dependencies()
    common = math.gcd(sr, 8000)
    # Bounded resampling; no model download, network or audio device.
    return signal.resample_poly(x, 8000 // common, sr // common, axis=0).astype(np.float32)


def transients(x, sr):
    """20ms energy-rise candidates, not a beat tracker or instrument detector."""
    np, _, _, signal = audio.dependencies()
    hop = round(sr * .02)
    count = len(x) // hop
    if count < 3:
        return np.array([], dtype=float)
    power = np.mean(np.square(x[:count * hop].reshape(count, hop, x.shape[1]), dtype=np.float64), axis=(1, 2))
    envelope = np.sqrt(power)
    rise = np.maximum(0, np.diff(envelope, prepend=envelope[0]))
    if float(rise.max()) < 1e-6:
        return np.array([], dtype=float)
    peaks, _ = signal.find_peaks(rise, height=max(float(rise.max()) * .15, 1e-6), distance=3)
    return peaks.astype(float) * hop / sr


def section_metrics(x, sr, start, end, name, onsets, bpm):
    np, _, _, signal = audio.dependencies()
    chunk = x[round(start * sr):round(end * sr)]
    rms = audio.rms(chunk)
    peak = float(np.max(np.abs(chunk)))
    mid = chunk.mean(axis=1)
    side = (chunk[:, 0] - chunk[:, -1]) * .5
    f, power = signal.welch(mid, fs=sr, nperseg=min(8192, len(mid)))
    power, f = power[f <= 4000], f[f <= 4000]
    total = float(power.sum())
    centroid = float(np.sum(f * power) / total) if total > 1e-20 else None
    corr = None
    if chunk.shape[1] == 2 and min(float(np.std(chunk[:, 0])), float(np.std(chunk[:, 1]))) > 1e-9:
        corr = float(np.corrcoef(chunk.T)[0, 1])
    hits = onsets[(onsets >= start) & (onsets < end)]
    rhythm = None
    if bpm is not None:
        sixteenth = 60 / bpm / 4
        errors = np.abs(hits / sixteenth - np.round(hits / sixteenth)) * sixteenth * 1000
        rhythm = {"bpm_hint": bpm, "grid": "sixteenth_from_time_zero",
                  "median_grid_error_ms": float(np.median(errors)) if len(errors) else None,
                  "p90_grid_error_ms": float(np.percentile(errors, 90)) if len(errors) else None}
    return {"name": name, "start_seconds": start, "end_seconds": end, "silent": peak < 1e-7,
            "rms_dbfs": audio.db(rms), "peak_dbfs": audio.db(peak),
            "crest_db": audio.db(peak) - audio.db(rms), "spectral_centroid_hz": centroid,
            "side_vs_mid_db": audio.db(audio.rms(side) / max(audio.rms(mid), 1e-8)),
            "stereo_correlation": corr, "onset_count": len(hits), "onsets_per_second": len(hits) / (end - start),
            "rhythm": rhythm}


def pitch_review(x):
    """Autocorrelation estimates for declared monophonic material, 32..1000Hz."""
    np, _, _, signal = audio.dependencies()
    mono = x.mean(axis=1)
    frame_size, hop = 1024, 160
    gate = max(float(np.max(np.abs(mono))) * .018, 1e-5)
    frames = []
    for start in range(0, len(mono) - frame_size + 1, hop):
        frame = mono[start:start + frame_size].astype(float)
        frame -= frame.mean()
        if audio.rms(frame) < gate:
            frames.append(None)
            continue
        corr = signal.fftconvolve(frame, frame[::-1], mode="full")[frame_size - 1:]
        energy = np.concatenate(([0.0], np.cumsum(frame * frame)))
        lags = np.arange(8, 251)
        norms = np.sqrt(energy[frame_size - lags] * (energy[frame_size] - energy[lags]))
        quality = corr[lags] / np.maximum(norms, 1e-20)
        peaks, _ = signal.find_peaks(quality)
        if not len(peaks):
            frames.append(None)
            continue
        best = float(quality[peaks].max())
        valid = peaks[quality[peaks] >= max(.75, best * .92)]
        if not len(valid):
            frames.append(None)
            continue
        lag = int(lags[valid[0]])
        # Quadratic refinement reduces integer-lag tuning quantization.
        denom = corr[lag - 1] - 2 * corr[lag] + corr[lag + 1]
        offset = .5 * (corr[lag - 1] - corr[lag + 1]) / denom if abs(denom) > 1e-20 else 0
        frequency = 8000 / (lag + float(np.clip(offset, -.5, .5)))
        midi = 69 + 12 * math.log2(frequency / 440)
        frames.append((midi, float(np.clip(quality[valid[0]], 0, 1))))
    events = []
    run = []
    def flush():
        if len(run) >= 3:
            values = [frames[i][0] for i in run]
            events.append({"start_seconds": (run[0] * hop + frame_size / 2) / 8000,
                           "end_seconds": (run[-1] * hop + frame_size / 2 + hop) / 8000,
                           "midi": round(float(np.median(values))), "median_midi": float(np.median(values)),
                           "confidence": float(np.median([frames[i][1] for i in run]))})
    for i, value in enumerate(frames):
        if value is None or (run and round(value[0]) != round(frames[run[-1]][0])):
            flush()
            run = []
        if value is not None:
            run.append(i)
    flush()
    voiced = [v[0] for v in frames if v is not None]
    histogram = [0] * 12
    for value in voiced:
        histogram[round(value) % 12] += 1
    notes = [e["midi"] for e in events]
    return {"method": "8khz_normalized_autocorrelation_heuristic", "voiced_fraction": len(voiced) / max(1, len(frames)),
            "pitch_range_midi": [float(np.percentile(voiced, 5)), float(np.percentile(voiced, 95))] if voiced else None,
            "pitch_classes": {name: count for name, count in zip(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"], histogram)},
            "estimated_note_count": len(events), "unique_midi_notes": sorted(set(notes)),
            "adjacent_repeated_note_fraction": sum(a == b for a, b in zip(notes, notes[1:])) / max(1, len(notes) - 1),
            "events": events[:128], "events_truncated": len(events) > 128,
            "limits": "Pitch candidates, not a transcription or tuning verdict. Polyphony, harmonics, distortion, slides, short gates and reverb may cause misses or octave errors. Histogram does not establish a key."}


def review(workspace, value):
    plan = Plan.model_validate(value)
    # Resolve every file first, including reference/stems, before audio processing.
    source = workspace.path(plan.source)
    reference = workspace.path(plan.reference) if plan.reference else None
    stem_paths = [workspace.path(s.path) for s in plan.stems]
    hashes = {str(p): digest(p) for p in [source, *stem_paths, *([reference] if reference else [])]}
    x, sr = audio.load(source)
    seconds = len(x) / sr
    previous = 0
    for section in plan.sections:
        if section.start < previous or section.end - section.start < .5 or section.end > seconds:
            raise ValueError("Sections must be ordered, nonoverlapping, at least 0.5 seconds and within source duration")
        previous = section.end
    # Preflight all stem headers/decodes and reference before recording success.
    np, sf, _, _ = audio.dependencies()
    for path in stem_paths:
        with sf.SoundFile(path) as f:
            if f.frames != len(x) or f.samplerate != sr:
                raise ValueError("Stems must match source sample rate and frame count")
    reference_report = audio.analyze(reference) if reference else None
    checkpoint("analyze", "Measuring bounced audio")
    metrics = audio.analyze_array(x, sr)
    metrics.update(sha256=hashes[str(source)], filename=source.name)
    onsets = transients(x, sr)
    sections = [(s.start, s.end, s.name) for s in plan.sections]
    if not sections:
        sections = [(float(start), min(float(start + 8), seconds), f"Window {i + 1}")
                    for i, start in enumerate(range(0, math.ceil(seconds), 8)) if start < seconds]
    timeline = [section_metrics(x, sr, start, end, name, onsets, plan.bpm) for start, end, name in sections]
    del x
    checkpoint("stems", "Inspecting declared stems")
    stems = []
    for i, (spec, path) in enumerate(zip(plan.stems, stem_paths)):
        checkpoint("stems", spec.name, i, len(plan.stems))
        stem, rate = audio.load(path)
        item = {"name": spec.name, "role": spec.role, "path": spec.path, "sha256": hashes[str(path)],
                "rms_dbfs": audio.db(audio.rms(stem)), "sample_peak_dbfs": audio.db(np.max(np.abs(stem))),
                "monophonic_declared": spec.monophonic}
        if spec.monophonic:
            item["pitch"] = pitch_review(reduced(stem, rate))
        stems.append(item)
        del stem
    checkpoint("interpret", "Separating measurements from proposed actions")
    observations, actions = [], []
    def add(kind, text, time=None, action=None):
        observations.append({"kind": kind, "text": text, "start_seconds": time, "evidence_type": "measured_signal"})
        if action:
            actions.append({"hypothesis": action, "start_seconds": time, "requires_listening": True, "automatic_edit": False})
    if "dynamics" in plan.focus:
        add("dynamics", f"Integrated loudness {metrics['integrated_lufs']:.2f} LUFS; estimated 4x true peak {metrics['true_peak_4x_dbtp_estimate']:.2f} dBTP; {metrics['clipped_samples']} clipped samples.")
        if metrics["clipped_samples"]:
            add("clipping", "Samples reach or exceed full scale.", action="Inspect the premaster gain and limiting, then compare a new bounce at matched loudness.")
    if "space" in plan.focus:
        add("space", f"Low-band side/mid ratio {metrics['lowband_side_vs_mid_db']:.1f} dB; mono-fold level change {metrics['mono_fold_loss_db']:.1f} dB.")
        if metrics["lowband_side_vs_mid_db"] > -12:
            actions.append({"hypothesis": "Check bass in mono; low-band side energy exceeds this review's -12 dB heuristic. Width may be intentional.", "start_seconds": None, "requires_listening": True, "automatic_edit": False})
    if "arrangement" in plan.focus:
        for before, after in zip(timeline, timeline[1:]):
            delta = after["rms_dbfs"] - before["rms_dbfs"]
            if abs(delta) >= 3 and not (before["silent"] or after["silent"]):
                add("section_energy", f"RMS changes {delta:+.1f} dB from {before['name']} to {after['name']}; this does not identify a drop or musical intent.", after["start_seconds"])
    if "balance" in plan.focus and stems:
        add("stem_balance", "Declared stem RMS: " + "; ".join(f"{s['name']} {s['rms_dbfs']:.1f} dBFS" for s in stems) + ". Not perceived loudness or masking detection.")
    if "rhythm" in plan.focus:
        add("rhythm", f"Detected {len(onsets)} energy-rise candidates at 20 ms resolution; these are not identified kick/snare hits or a groove-quality score.")
    if "melody" in plan.focus:
        pitched = [s for s in stems if "pitch" in s]
        if not pitched:
            actions.append({"hypothesis": "Provide an aligned dry monophonic lead stem to inspect note contour; full-mix melody quality remains unassessed.", "start_seconds": None, "requires_listening": True, "automatic_edit": False})
        for stem in pitched:
            add("pitch_candidates", f"{stem['name']}: {stem['pitch']['estimated_note_count']} estimated note spans, {stem['pitch']['voiced_fraction']:.0%} voiced frames. No artistic or tuning verdict.")
    comparison = None
    if reference_report:
        comparison = {"metrics": reference_report,
                      "level_match_db": reference_report["integrated_lufs"] - metrics["integrated_lufs"],
                      "crest_delta_db": metrics["crest_db"] - reference_report["crest_db"],
                      "spectral_balance_delta_db": [{"hz": a["hz"], "delta": (a["rms_dbfs"] - metrics["integrated_lufs"]) - (b["rms_dbfs"] - reference_report["integrated_lufs"])}
                                                    for a in metrics["spectrum"] for b in reference_report["spectrum"] if a["hz"] == b["hz"]],
                      "limit": "Level-normalized metrics only; reference duration/arrangement may differ. No artist, source separation or quality equivalence inferred."}
    preserved = all(digest(p) == hashes[str(p)] for p in [source, *stem_paths, *([reference] if reference else [])])
    if not preserved:
        raise ValueError("An input changed during review; discard this analysis")
    result = {"schema_version": 1, "mode": "internal_signal_review", "source": metrics,
              "plan": plan.model_dump(exclude_none=True), "timeline": timeline, "stems": stems,
              "reference": comparison, "observations": observations, "proposed_actions": actions,
              "source_files_preserved": preserved,
              "assumptions": {"bpm": "user supplied hint, not inferred", "grid_origin_seconds": 0,
                              "onset_resolution_ms": 20, "centroid_band_hz": [0, 4000],
                              "focus": "filters narrative observations; timeline/stem measurements still collected"},
              "review": {"method": "file_signal_analysis", "speaker_playback": False,
                         "perceptual_listening": False, "creative_acceptance": "pending"},
              "limits": ["No audio semantic model or human audition is available in this mode.",
                         "Measurements cannot establish whether a hook is memorable, a patch sounds expensive, a mix is pleasing or a style is authentic.",
                         "Energy rises and grid errors are heuristics; swing, syncopation, negative space and section changes may be intentional.",
                         "Silence and anti-phase cancellation can prevent centroid/pitch estimates. Supply dry stems for useful melody diagnostics.",
                         "Proposed actions require a musical decision; no automatic corrections or user preference are inferred."]}
    checkpoint("write", "Writing a new review packet")
    output = workspace.new_render()
    result["report_path"] = workspace.relative(output / "review.json")
    checkpoint("record", "Recording measured evidence for recall")
    result["event_id"] = Ledger(workspace).append("review", ["listen", "internal_signal_review"], result)
    write_json(output / "review.json", result)
    return result
