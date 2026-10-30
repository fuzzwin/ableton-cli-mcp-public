"""Silent workflow exercise using this project's existing test bounces only."""
import argparse
import json
from pathlib import Path
from cli_anything.ableton.production.api import Production


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--premaster',required=True)
    parser.add_argument('--reference',required=True)
    parser.add_argument('--sample',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    p=Production(args.workspace)
    plans={
        'creative-smoke-versions.json':{'path':args.premaster,'intent':'Technical test of master directions; no human preference recorded.','versions':[{'name':s,'profile':s} for s in ['dynamic','balanced','dense']]},
        'creative-smoke-reference.json':{'label':'Internal pipeline example, not a user-selected reference','reference':{'path':args.reference,'start_seconds':0.,'end_seconds':8.},'candidate':{'path':args.premaster,'start_seconds':0.,'end_seconds':8.},'focus':['bass','dynamics'],'user_notes':'Technical workflow exercise only.'},
        'creative-smoke-sample.json':{'path':args.sample,'start_seconds':0.,'end_seconds':.4,'reverse':True,'fade_in_ms':2.,'fade_out_ms':15.,'peak_normalize_dbfs':-3.}}
    for name,plan in plans.items():
        target=p.workspace.path(name,exists=False)
        with target.open('x') as f:json.dump(plan,f,indent=2)
    versions=p.master_versions('creative-smoke-versions.json')
    reference=p.reference('creative-smoke-reference.json')
    sample=p.sample_edit('creative-smoke-sample.json')
    summary={'speaker_playback':False,'source_preserved':versions['source_preserved'],
        'versions':[{'name':v['name'],'lufs':v['metrics']['integrated_lufs'],'true_peak':v['metrics']['true_peak_4x_dbtp_estimate'],'comparison_lufs':v['comparison_lufs']} for v in versions['versions']],
        'reference_section_frames':reference['reference_source']['end_frame']-reference['reference_source']['start_frame'],
        'reference_scope':'Internal test input, not a supplied commercial reference or subjective acceptance.',
        'edited_sample_frames':sample['frames'],'method_count':len(p.methods()['methods']),
        'version_event_id':versions['event_id'],'creative_winner':versions['creative_winner']}
    args.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
