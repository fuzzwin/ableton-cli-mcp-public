"""Child-only plugin render. Never opens an audio output device."""
import json
import sys
from pathlib import Path


def main():
    import resource
    # Bound noisy vendor logs and CPU use; this is not an OS sandbox.
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    import numpy as np
    import soundfile as sf
    from pedalboard import load_plugin
    destination = Path(sys.argv[2])
    try:
        plugin = load_plugin(sys.argv[1])
        parameter_names=list(plugin.parameters)[:512]
        sr, seconds = 44100, 4.0
        instrument = bool(plugin.is_instrument)
        if instrument:
            midi = []
            for note in [60]:
                midi.extend([(bytes([0x90, note, 100]), 0.1), (bytes([0x80, note, 0]), 2.0)])
            midi.sort(key=lambda m:m[1])
            y = plugin(midi, duration=seconds, sample_rate=sr, num_channels=2, buffer_size=512, reset=True)
        else:
            rng = np.random.default_rng(0)
            source = rng.normal(0, .025, (2, int(sr * seconds))).astype(np.float32)
            source[:, sr * 2:] = 0
            y = plugin(source, sr, reset=True)
        finite = bool(np.isfinite(y).all())
        peak = float(np.max(np.abs(y))) if finite and y.size else 0
        result = {"status": "rendered" if finite and peak > 1e-6 else "silent_or_invalid",
                  "instrument": instrument, "peak": peak, "finite": finite,
                  "parameters": parameter_names, "buffer_size":512, "sample_rate": sr,
                  "stimulus": "Sorted C4 note60, velocity100; on0.1s off2.0s; buffer512" if instrument else "seeded quiet noise then tail"}
        if finite and peak > 1e-6:
            # Float preserves even an unexpectedly hot probe without integer clipping.
            sf.write(destination / "probe.wav", np.asarray(y).T, sr, subtype="FLOAT")
    except Exception as exc:
        result = {"status": "load_error", "reason": str(exc)[:2000]}
    (destination / "probe-result.json").write_text(json.dumps(result, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
