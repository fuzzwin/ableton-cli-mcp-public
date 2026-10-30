"""Use copies of an existing bounce to exercise the silent file pipeline."""
import argparse
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from cli_anything.ableton.production.api import Production
from cli_anything.ableton.production.workspace import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-project", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    root.mkdir(exist_ok=True)
    destination = root / "ion-drive-test-inputs"
    destination.mkdir()  # Never overwrite an earlier demo.
    stems, sources, silent = [], [], []
    roles = ["kick", "bass", "sub", "drums", "drums", "drums", "drums", "drums", "lead", "lead", "pad", "fx", "fx"]
    for source, role in zip(sorted((args.source_project / "Samples/Imported").glob("*.wav")), roles):
        before = digest(source)
        with sf.SoundFile(source) as f:
            start = int(96 * 4 * 60 / 140 * f.samplerate)
            length = int(16 * 4 * 60 / 140 * f.samplerate)
            f.seek(start)
            x = f.read(length, dtype="float32", always_2d=True)
            sr = f.samplerate
        sources.append({"filename": source.name, "sha256_before": before, "sha256_after": digest(source)})
        if float(np.max(np.abs(x))) < 1e-7:
            silent.append(source.name)
            continue
        output = destination / source.name
        sf.write(output, x, sr, subtype="PCM_24")
        stems.append({"path": str(output.relative_to(root)), "role": role})
    plan = {"stems": stems, "target_lufs": -12.0, "ceiling_dbtp": -1.0, "max_attempts": 2,
            "tags": ["techno", "ion-drive", "pipeline-smoke"]}
    (root / "ion-drive-smoke-plan.json").write_text(json.dumps(plan, indent=2))
    production = Production(root)
    result = production.mix("ion-drive-smoke-plan.json")
    report = {"demo": "16-bar file-only pipeline exercise; not a creatively approved remix", "sources": sources,
              "source_files_unchanged": all(s["sha256_before"] == s["sha256_after"] for s in sources),
              "skipped_silent_section_stems": silent, "stem_count": len(stems), "result": result}
    (root / "production-smoke.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"source_files_unchanged": report["source_files_unchanged"], "stem_count": len(stems),
                      "event_id": result["event_id"], "output_directory": result["output_directory"],
                      "lufs": result["master"]["integrated_lufs"], "true_peak": result["master"]["true_peak_4x_dbtp_estimate"],
                      "technical_pass": result["technical_pass"], "speaker_playback": False}))


if __name__ == "__main__":
    main()
