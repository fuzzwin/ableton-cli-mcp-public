"""Bounded stem mixing and linked mastering to new files only."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from . import audio
from .workspace import digest, timestamp, write_json
from .ledger import Ledger
from .progress import checkpoint


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Stem(Strict):
    path: str = Field(min_length=1, max_length=500)
    role: Literal["kick", "sub", "bass", "lead", "pad", "drums", "fx", "other"]
    gain_db: float = Field(default=0, ge=-24, le=24)
    pan: float = Field(default=0, ge=-1, le=1)
    highpass_hz: float = Field(default=0, ge=0, le=1000)
    compress: bool = False
    duck_db: float = Field(default=0, ge=0, le=12)


class Plan(Strict):
    stems: list[Stem] = Field(min_length=1, max_length=24)
    duck_source: str | None = None
    auto_balance: bool = False
    target_lufs: float = Field(default=-12, ge=-20, le=-8)
    ceiling_dbtp: float = Field(default=-1, ge=-3, le=-0.5)
    max_attempts: int = Field(default=2, ge=1, le=2)
    tags: list[str] = Field(default_factory=list, max_length=20)


def master(x, sr, target=-12.0, ceiling=-1.0, max_attempts=2, release_ms=80.0, lookahead_ms=5.0, reduction_budget_db=6.0):
    np, _, _, signal = audio.dependencies()
    from scipy.ndimage import maximum_filter1d
    if not -20 <= target <= -8 or not -3 <= ceiling <= -.5 or type(max_attempts) is not int or not 1 <= max_attempts <= 2:
        raise ValueError("Master limits: -20..-8 LUFS, -3..-0.5 dBTP, 1..2 candidates")
    if not 20 <= release_ms <= 250 or not 1 <= lookahead_ms <= 10 or not 1 <= reduction_budget_db <= 12:
        raise ValueError("Invalid limiter timing or reduction budget")
    source_lufs = audio.loudness(x, sr)
    drive = target - source_lufs
    candidates = []
    best_audio = None
    best_score = float("inf")
    ceiling_linear = 10 ** (ceiling / 20)
    for attempt in range(max_attempts):
        y = x * 10 ** (drive / 20)
        peaks = np.max(np.abs(y), axis=1)
        look = max(1, int(sr * lookahead_ms / 1000))
        ahead = maximum_filter1d(peaks, size=2 * look + 1, origin=-look, mode="nearest")
        required = np.minimum(1, ceiling_linear / np.maximum(ahead, 1e-8))
        release = float(np.exp(-1 / (sr * release_ms / 1000)))
        smooth, _ = signal.lfilter([1 - release], [1, -release], required, zi=[release * required[0]])
        gains = np.minimum(required, smooth)
        y *= gains[:, None]
        correction = min(1.0, ceiling_linear / max(audio.true_peak(y), 1e-9))
        y *= correction
        measured = audio.loudness(y, sr)
        reduction = -audio.db(float(np.min(gains)) * correction)
        report = {"attempt": attempt + 1, "drive_db": drive, "integrated_lufs": measured,
                  "true_peak_4x_dbtp_estimate": audio.db(audio.true_peak(y)),
                  "maximum_gain_reduction_db": reduction,
                  "loudness_target_met": abs(measured - target) <= 1.0,
                  "reduction_budget_met": reduction <= reduction_budget_db}
        candidates.append(report)
        score = abs(measured - target) + max(0, reduction - reduction_budget_db) * 2
        if score < best_score:
            best_audio, best_score = y.astype(np.float32), score
            selected = attempt + 1
        if report["loudness_target_met"] or reduction > reduction_budget_db:
            break
        drive += min(1.5, max(-1.5, target - measured))
    return best_audio, {"candidates": candidates, "selected_attempt": selected,
                        "target_lufs": target, "ceiling_dbtp": ceiling,
                        "release_ms": release_ms, "lookahead_window_ms": lookahead_ms * 2,
                        "reduction_budget_db": reduction_budget_db,
                        "creative_acceptance": "pending", "perceptual_listening": False}


def active_rms(x, sr):
    np, _, _, _ = audio.dependencies()
    block = max(1, int(sr * .05))
    n = len(x) // block
    energy = np.sqrt(np.mean(x[:n * block].reshape(n, block, x.shape[1]) ** 2, axis=(1, 2)))
    return float(np.percentile(energy, 90))


def render_mix(workspace, raw_plan):
    np, sf, _, signal = audio.dependencies()
    try:
        plan = Plan.model_validate(raw_plan)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    paths = [workspace.path(s.path) for s in plan.stems]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate stem paths")
    try:
        infos = [sf.info(p) for p in paths]
    except RuntimeError as exc:
        raise ValueError("Unable to inspect bounced stem: " + str(exc)) from exc
    sr, frames = infos[0].samplerate, infos[0].frames
    if any(i.samplerate != sr or i.frames != frames for i in infos):
        raise ValueError("Stems must share sample rate and frame count; align them before rendering")
    # Validate every source before writing any output or mixing allocations.
    if sum(i.frames * i.channels for i in infos) > 500_000_000:
        raise ValueError("Combined stem work budget exceeded")
    for p in paths:
        audio.load(p)
    key = None
    kick_level = None
    if plan.duck_source is not None:
        key_path = workspace.path(plan.duck_source)
        if key_path not in paths or plan.stems[paths.index(key_path)].role != "kick":
            raise ValueError("Ducking source must identify a supplied kick stem")
        key_audio, _ = audio.load(key_path)
        kick_level = active_rms(key_audio, sr)
        envelope = np.max(np.abs(key_audio), axis=1)
        decay = np.exp(-1 / (sr * .060))
        envelope = signal.lfilter([1 - decay], [1, -decay], envelope)
        key = np.clip(envelope / max(float(np.percentile(envelope, 95)), 1e-8), 0, 1)
    if any(s.duck_db > 0 for s in plan.stems) and key is None:
        raise ValueError("Ducked stems require a kick duck_source")
    if plan.auto_balance and kick_level is None:
        raise ValueError("Opt-in automatic role balance requires a kick duck_source")
    mix = np.zeros((frames, 2), dtype=np.float32)
    checkpoint("mix", "Processing aligned stems",0,len(paths))
    moves, hashes = [], []
    relative_targets = {"kick": 0, "sub": -4, "bass": -6, "lead": -5, "pad": -12, "drums": -8, "fx": -12, "other": -10}
    for stem, path in zip(plan.stems, paths):
        x, _ = audio.load(path)
        hashes.append({"path": stem.path, "sha256": digest(path)})
        automatic = 0.0
        if plan.auto_balance and stem.role != "kick":
            automatic = float(np.clip(audio.db(kick_level) + relative_targets[stem.role] - audio.db(active_rms(x, sr)), -3, 3))
        if stem.highpass_hz:
            x = signal.sosfilt(signal.butter(2, stem.highpass_hz, btype="highpass", fs=sr, output="sos"), x, axis=0)
        if stem.compress:
            from pedalboard import Compressor
            x = Compressor(threshold_db=-18, ratio=2, attack_ms=15, release_ms=100)(x.T.astype(np.float32), sr).T
        if x.shape[1] == 1:
            # Equal-power mono pan; existing stereo uses attenuation-only balance.
            theta = (stem.pan + 1) * np.pi / 4
            x = x * np.array([np.cos(theta), np.sin(theta)])
        else:
            x = x * np.array([min(1, 1 - stem.pan), min(1, 1 + stem.pan)])
        if stem.duck_db:
            x *= (10 ** (-stem.duck_db * key / 20))[:, None]
        mix += (x * 10 ** ((stem.gain_db + automatic) / 20)).astype(np.float32)
        moves.append({**stem.model_dump(), "automatic_gain_db": automatic})
        checkpoint("mix","Processing aligned stems",len(moves),len(paths))
    peak = float(np.max(np.abs(mix)))
    if peak < 1e-7:
        raise ValueError("Mixed stems cancel to silence")
    headroom_gain = min(1.0, 10 ** (-6 / 20) / peak)
    mix *= headroom_gain
    checkpoint("master")
    mastered, mastering = master(mix, sr, plan.target_lufs, plan.ceiling_dbtp, plan.max_attempts)
    checkpoint("write")
    output = workspace.new_render()
    sf.write(output / "premaster.wav", mix, sr, subtype="PCM_24")
    sf.write(output / "master.wav", mastered, sr, subtype="PCM_24")
    checkpoint("checks")
    measured = audio.analyze(output / "master.wav")
    passed = measured["clipped_samples"] == 0 and measured["true_peak_4x_dbtp_estimate"] <= plan.ceiling_dbtp + .02
    report = {"schema_version": 1, "created": timestamp(), "inputs": hashes,
              "plan": plan.model_dump(), "moves": moves, "headroom_gain_db": audio.db(headroom_gain),
              "mastering": mastering, "master": measured, "technical_pass": passed,
              "output_directory": workspace.relative(output), "speaker_playback": False,
              "renderer": "file DSP; not native Ableton export", "source_files_preserved": True}
    checkpoint("record")
    write_json(output / "report.json", report)
    event_id = Ledger(workspace).append("render", plan.tags, report)
    return {"event_id": event_id, **report}


def render_master(workspace, source, target=-12.0, ceiling=-1.0):
    _, sf, _, _ = audio.dependencies()
    path = workspace.path(source)
    x, sr = audio.load(path)
    checkpoint("master")
    y, decisions = master(x, sr, target, ceiling)
    checkpoint("write")
    output = workspace.new_render()
    sf.write(output / "master.wav", y, sr, subtype="PCM_24")
    checkpoint("checks")
    report = {"input": {"path": source, "sha256": digest(path)}, "mastering": decisions,
              "master": audio.analyze(output / "master.wav"), "output_directory": workspace.relative(output),
              "speaker_playback": False, "source_files_preserved": True,
              "renderer": "file DSP; not native Ableton export"}
    checkpoint("record")
    write_json(output / "report.json", report)
    event_id = Ledger(workspace).append("render", ["mastering"], report)
    return {"event_id": event_id, **report}
