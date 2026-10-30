"""Maintainer: export reviewed source only into a new empty public checkout.

Never copy the private Git directory, runtime reports, inventories or audio.
Review the manifest and content scan before publishing; this is not a secret scanner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
FILES=['.github/workflows/tests.yml', '.gitignore', 'LICENSE', 'NOTICE', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md', 'USER_GUIDE.md', 'acceptance/CREATIVE-REQUIREMENTS.md', 'acceptance/PRODUCTION-REQUIREMENTS.md', 'acceptance/PROGRESS-REQUIREMENTS.md', 'acceptance/PROMPT-REQUIREMENTS.md', 'acceptance/PUBLIC-REQUIREMENTS.md', 'acceptance/REQUIREMENTS.txt', 'acceptance/TEST.md', 'acceptance/prompt-cases.json', 'acceptance/test_contract.py', 'acceptance/test_creative.py', 'acceptance/test_interfaces.py', 'acceptance/test_production.py', 'acceptance/test_progress.py', 'acceptance/test_prompting.py', 'acceptance/test_public.py', 'acceptance/test_transport.py', 'cli_anything/ableton/__init__.py', 'cli_anything/ableton/__main__.py', 'cli_anything/ableton/ableton_cli.py', 'cli_anything/ableton/als.py', 'cli_anything/ableton/bridge.py', 'cli_anything/ableton/client.py', 'cli_anything/ableton/install.py', 'cli_anything/ableton/mcp_server.py', 'cli_anything/ableton/native_remote.py', 'cli_anything/ableton/policy.py', 'cli_anything/ableton/preparation.py', 'cli_anything/ableton/production/__init__.py', 'cli_anything/ableton/production/api.py', 'cli_anything/ableton/production/audio.py', 'cli_anything/ableton/production/data/knowledge.json', 'cli_anything/ableton/production/data/knowledge.schema.json', 'cli_anything/ableton/production/data/methods.json', 'cli_anything/ableton/production/knowledge.py', 'cli_anything/ableton/production/ledger.py', 'cli_anything/ableton/production/plugins.py', 'cli_anything/ableton/production/probe_worker.py', 'cli_anything/ableton/production/progress.py', 'cli_anything/ableton/production/render.py', 'cli_anything/ableton/production/workflows.py', 'cli_anything/ableton/production/workspace.py', 'cli_anything/ableton/service.py', 'cli_anything/ableton/skills/SKILL.md', 'cli_anything/ableton/utils/__init__.py', 'cli_anything/ableton/utils/repl_skin.py', 'docs/CREATIVE-WORKFLOWS.md', 'docs/DEMO-MCP-CHECK.json', 'docs/DEMO-RESULTS.json', 'docs/INVOCATION-PROMPT.md', 'docs/NATIVE-CAPABILITIES.md', 'docs/PRODUCTION-PROGRESS.md', 'docs/PUBLIC-README.md', 'docs/VERIFICATION.md', 'docs/proof-visual.html', 'examples/master-versions-plan.json', 'examples/reference-plan.json', 'examples/sample-edit-plan.json', 'examples/stem-plan.json', 'examples/task-request.json', 'examples/tempo.json', 'licenses/CLI-Anything-Apache-2.0.txt', 'mcp-config.example.json', 'pyproject.toml', 'scripts/creative_smoke.py', 'scripts/demo_songs.py', 'scripts/export_public.py', 'scripts/production_mcp_probe.py', 'scripts/production_smoke.py', 'scripts/proof_check.py', 'scripts/proof_visual.py', 'scripts/run_proof_visual.py', 'skills/cli-anything-ableton/SKILL.md', 'task.json', 'uv.lock']


def export(output):
    destination=Path(output)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Public export destination must be a new or empty directory')
    destination.mkdir(parents=True,exist_ok=True)
    for relative in FILES:
        source=ROOT/relative
        if (not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(ROOT.resolve())
                or any(p.is_symlink() for p in source.parents if p != ROOT and p.is_relative_to(ROOT))):
            raise ValueError('Public source must be a regular contained file: '+relative)
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    readme=ROOT/'docs/PUBLIC-README.md'
    if not readme.is_file():readme=ROOT/'README.md'
    shutil.copyfile(readme,destination/'README.md')
    # A packaged README has a different base directory; use stable public URLs.
    import re
    package_readme=re.sub(r'\]\(([^)]+)\)',lambda m: ']('+m.group(1)+')' if '://' in m.group(1) or m.group(1).startswith('#') else '](https://github.com/fuzzwin/ableton-cli-mcp-public/blob/main/'+m.group(1)+')',readme.read_text())
    (destination/'cli_anything/ableton/README.md').write_text(package_readme)
    (destination/'AGENTS.md').write_text('# Public Ableton connector\n\nRead USER_GUIDE.md and acceptance requirements before changes. Preserve original audio and silent defaults. Do not commit bridge config, tokens, audio, plugin binaries, inventories or evidence ledgers. Use actual Proof Loop reports and keep native mutation, file checks and creative acceptance separate. Meaningful changes need a fresh independent review and at most two repair rounds.\n')
    manifest={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'PUBLIC-MANIFEST.json').write_text(json.dumps({'schema_version':1,'scope':'Fresh public source snapshot; no private history or runtime assets','sha256':manifest},indent=2)+'\n')
    return {'files':len(manifest)+1,'output':str(destination)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    print(json.dumps(export(parser.parse_args().output)))
