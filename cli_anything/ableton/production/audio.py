"""Numerical review of bounced files. This module has no playback API."""
import math
from pathlib import Path
from .workspace import digest

MAX_FRAMES = 30_000_000
BANDS = [(25, 120), (120, 400), (400, 2500), (2500, 6000), (6000, 16000)]


def dependencies():
    try:
        import numpy as np
        import soundfile as sf
        import pyloudnorm as pyln
        from scipy import signal
        return np, sf, pyln, signal
    except ImportError as exc:
        raise ValueError("Install audio extras: uv sync --extra audio") from exc


def db(value):
    return max(-160.0, 20 * math.log10(max(float(value), 1e-8)))


def load(path, min_seconds=0.5):
    np, sf, _, _ = dependencies()
    if Path(path).suffix.lower() not in {".wav", ".aiff", ".aif", ".flac"}:
        raise ValueError("Use a bounced WAV, AIFF or FLAC file")
    try:
        with sf.SoundFile(path) as f:
            if f.channels not in (1, 2) or not 8000 <= f.samplerate <= 192000:
                raise ValueError("Audio must be mono/stereo at 8..192 kHz")
            if f.frames > MAX_FRAMES or f.frames / f.samplerate > 600 or f.frames / f.samplerate < min_seconds:
                raise ValueError(f"Audio must be {min_seconds}..600 seconds and at most 30 million frames")
            x = f.read(dtype="float32", always_2d=True)
            sr = f.samplerate
    except RuntimeError as exc:
        raise ValueError("Unable to decode bounced audio: " + str(exc)) from exc
    if not np.isfinite(x).all():
        raise ValueError("Audio contains nonfinite samples")
    if float(np.max(np.abs(x))) < 1e-7:
        raise ValueError("Audio is silent; do not promote this render")
    return x, sr


def true_peak(x):
    """4x FIR interpolation with overlap; bounded temporary allocation."""
    np, _, _, signal = dependencies()
    peak = 0.0
    for start in range(0, len(x), 65536):
        left, right = max(0, start - 64), min(len(x), start + 65536 + 64)
        chunk = signal.resample_poly(x[left:right], 4, 1, axis=0)
        # Ignore the artificial zero-padded ends of interior chunks.
        valid_start = (start - left) * 4
        valid_end = (min(len(x), start + 65536) - left) * 4
        peak = max(peak, float(np.max(np.abs(chunk[valid_start:valid_end]))))
    return peak


def loudness(x, sr):
    _, _, pyln, _ = dependencies()
    value = float(pyln.Meter(sr).integrated_loudness(x))
    if not math.isfinite(value):
        raise ValueError("Audio is below the loudness gate")
    return value


def rms(x):
    np, _, _, _ = dependencies()
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def analyze_array(x, sr):
    np, _, _, signal = dependencies()
    if x.ndim != 2 or x.shape[1] not in (1, 2) or not np.isfinite(x).all():
        raise ValueError("Invalid audio array")
    peak = float(np.max(np.abs(x)))
    spectrum = []
    for low, high in BANDS:
        high = min(high, sr * 0.49)
        if high <= low:
            continue
        filtered = signal.sosfilt(signal.butter(3, [low, high], btype="bandpass", fs=sr, output="sos"), x, axis=0)
        spectrum.append({"hz": [low, high], "rms_dbfs": db(rms(filtered))})
    mid = x.mean(axis=1)
    side = (x[:, 0] - x[:, -1]) * 0.5
    low_filter = signal.butter(3, min(120, sr * .4), fs=sr, output="sos")
    low_mid, low_side = signal.sosfilt(low_filter, mid), signal.sosfilt(low_filter, side)
    correlation = None
    if x.shape[1] == 2 and np.std(x[:, 0]) > 1e-9 and np.std(x[:, 1]) > 1e-9:
        correlation = float(np.corrcoef(x.T)[0, 1])
    windows = []
    for start in range(0, len(x), sr * 3):
        chunk = x[start:start + sr * 3]
        windows.append({"start_seconds": start / sr, "rms_dbfs": db(rms(chunk)), "peak_dbfs": db(np.max(np.abs(chunk)))})
    return {"duration_seconds": len(x) / sr, "sample_rate": sr, "channels": x.shape[1],
            "integrated_lufs": loudness(x, sr), "sample_peak_dbfs": db(peak),
            "true_peak_4x_dbtp_estimate": db(true_peak(x)),
            "clipped_samples": int(np.sum(np.abs(x) >= 1)), "finite": True,
            "crest_db": db(peak) - db(rms(x)), "stereo_correlation": correlation,
            "side_vs_mid_db": db(rms(side) / max(rms(mid), 1e-8)),
            "lowband_side_vs_mid_db": db(rms(low_side) / max(rms(low_mid), 1e-8)),
            "mono_fold_loss_db": db(rms(mid) / max(rms(x), 1e-8)),
            "spectrum": spectrum, "windows": windows,
            "review": {"method": "file_signal_analysis", "speaker_playback": False,
                       "perceptual_listening": False, "creative_acceptance": "pending"}}


def analyze(path):
    x, sr = load(path)
    result = analyze_array(x, sr)
    result["sha256"] = digest(path)
    result["filename"] = Path(path).name
    return result


def compare(path, reference):
    a, b = analyze(path), analyze(reference)
    # Metrics are level independent or explicitly normalized to the same LUFS.
    return {"candidate": a, "reference": b, "level_match_db": b["integrated_lufs"] - a["integrated_lufs"],
            "crest_delta_db": a["crest_db"] - b["crest_db"],
            "spectral_balance_delta_db": [
                {"hz": x["hz"], "delta": (x["rms_dbfs"] - a["integrated_lufs"]) - (y["rms_dbfs"] - b["integrated_lufs"])}
                for x, y in zip(a["spectrum"], b["spectrum"]) if x["hz"] == y["hz"]],
            "limit": "Diagnostic comparison; no audio playback or claim of perceptual equivalence."}
