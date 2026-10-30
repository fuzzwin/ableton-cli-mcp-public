import asyncio
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import numpy as np
import soundfile as sf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from cli_anything.ableton.production import audio, knowledge
from cli_anything.ableton.production.workflows import reference_brief, edit_sample, master_versions
from cli_anything.ableton.production.workspace import Workspace, digest
from cli_anything.ableton.mcp_server import create_server


class Creative(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = Workspace(self.root)
        self.sr = 16000
        t = np.arange(self.sr * 2) / self.sr
        self.x = np.column_stack([.1 * np.sin(2*np.pi*180*t), .1*np.sin(2*np.pi*180*t)]).astype(np.float32)
        sf.write(self.root/'mix.wav', self.x, self.sr, subtype='FLOAT')
        sf.write(self.root/'reference.wav', self.x * .5, self.sr, subtype='FLOAT')

    def tearDown(self):
        self.tmp.cleanup()

    def brief(self):
        return {'label':'User example','reference':{'path':'reference.wav','start_seconds':.5,'end_seconds':1.5},
                'candidate':{'path':'mix.wav','start_seconds':.5,'end_seconds':1.5},'focus':['bass','width'],'user_notes':'I like the sense of space'}

    def experiment(self):
        return {'path':'mix.wav','intent':'Compare density and transient budget','versions':[{'name':p,'profile':p} for p in ['dynamic','balanced','dense']]}

    def test_methods_cover_workflow_with_source_boundaries(self):
        methods = knowledge.methods(limit=20)['methods']
        original = {'edit-cleanly','sample-purpose','mix-priorities','effects-depth','style-laboratory','reference-brief','master-directions'}
        expanded = {'kick-bass-pocket','snare-clap-layer','hat-pocket','loop-context','filtered-room','rhythmic-delay-throws','parallel-color','fullsong-contrast'}
        identities = [item['id'] for item in methods]
        self.assertEqual(set(identities), original | expanded)
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(len(knowledge.methods()['methods']), 8)
        for item in methods:
            for key in ['intent','steps','execute_here','native_or_manual','compare','sources']:
                self.assertTrue(item[key])
            self.assertTrue(all(s['url'].startswith('https://') and s['boundary'] for s in item['sources']))
        self.assertTrue(knowledge.methods('effects')['methods'])

    def test_reference_sections_notes_and_no_audio_copy(self):
        before = digest(self.root/'reference.wav')
        result = reference_brief(self.w,self.brief())
        self.assertEqual(result['reference_source']['start_frame'],8000)
        self.assertEqual(result['reference_source']['end_frame'],24000)
        self.assertEqual(result['user_notes'],'I like the sense of space')
        self.assertAlmostEqual(result['comparison']['candidate_level_match_db'],-6.0206,delta=.01)
        self.assertLess(max(abs(b['delta']) for b in result['comparison']['spectral_delta_db']),.01)
        self.assertEqual(digest(self.root/'reference.wav'),before)
        self.assertFalse(list(self.w.path(result['output_directory']).glob('*.wav')))

    def test_invalid_reference_section_has_no_output(self):
        for start,end in [(1.5,.5),(0,3),(.1,.2)]:
            plan=self.brief();plan['reference'].update(start_seconds=start,end_seconds=end)
            with self.assertRaises(ValueError):reference_brief(self.w,plan)
        self.assertFalse((self.root/'renders').exists())

    def test_reference_path_escape_rejected(self):
        plan=self.brief();plan['reference']['path']='../outside.wav'
        with self.assertRaises((ValueError,OSError)):reference_brief(self.w,plan)
        self.assertFalse((self.root/'renders').exists())

    def test_short_sample_trim_reverse_and_source_preserved(self):
        source=np.linspace(.01,.2,480,dtype=np.float32)
        sf.write(self.root/'short.wav',source,self.sr,subtype='FLOAT')
        before=digest(self.root/'short.wav')
        result=edit_sample(self.w,{'path':'short.wav','start_seconds':.005,'end_seconds':.025,'reverse':True,'fade_in_ms':0.,'fade_out_ms':0.})
        y,sr=sf.read(self.w.path(result['output_path']),dtype='float32',always_2d=True)
        self.assertEqual(len(y),320)
        self.assertTrue(np.allclose(y[:,0],source[80:400][::-1],atol=2e-7))
        self.assertEqual(digest(self.root/'short.wav'),before)

    def test_sample_fades_and_explicit_normalization(self):
        result=edit_sample(self.w,{'path':'mix.wav','fade_in_ms':5.,'fade_out_ms':5.,'peak_normalize_dbfs':-3.})
        y,_=sf.read(self.w.path(result['output_path']),always_2d=True)
        self.assertTrue(np.all(y[0]==0) and np.all(y[-1]==0))
        self.assertAlmostEqual(audio.db(np.max(np.abs(y))),-3,delta=.01)

    def test_sample_clipping_and_invalid_fades_rejected(self):
        sf.write(self.root/'hot.wav',self.x*8,self.sr,subtype='FLOAT')
        for plan in [{'path':'hot.wav','gain_db':12.},{'path':'mix.wav','end_seconds':.02,'fade_in_ms':20.,'fade_out_ms':20.}]:
            with self.assertRaises(ValueError):edit_sample(self.w,plan)
        self.assertFalse((self.root/'renders').exists())

    def test_extreme_finite_sample_normalizes_without_overflow(self):
        sf.write(self.root/'extreme.wav',np.full((self.sr,1),1e38,dtype=np.float32),self.sr,subtype='FLOAT')
        result=edit_sample(self.w,{'path':'extreme.wav','gain_db':12.,'peak_normalize_dbfs':-3.})
        y,_=sf.read(self.w.path(result['output_path']),always_2d=True)
        self.assertTrue(np.isfinite(y).all())
        self.assertAlmostEqual(audio.db(np.max(np.abs(y))),-3,delta=.01)

    def test_version_names_and_unknown_parent_rejected(self):
        for names in [('same','SAME'),('a','a-level-matched'),('../bad','ok')]:
            plan=self.experiment();plan['versions']=[{'name':n,'profile':'balanced'} for n in names]
            with self.assertRaises(ValueError):master_versions(self.w,plan)
        plan=self.experiment();plan['parent_event_id']='unknown'
        with self.assertRaises(ValueError):master_versions(self.w,plan)
        self.assertFalse((self.root/'renders').exists())

    def test_versions_same_source_and_matched_copies(self):
        before=digest(self.root/'mix.wav')
        result=master_versions(self.w,self.experiment())
        self.assertEqual(result['source_sha256'],before)
        self.assertEqual(digest(self.root/'mix.wav'),before)
        self.assertIsNone(result['creative_winner'])
        measured=[]
        for v in result['versions']:
            self.assertLessEqual(v['metrics']['true_peak_4x_dbtp_estimate'],-.98)
            self.assertLessEqual(v['comparison_attenuation_db'],0)
            measured.append(audio.analyze(self.w.path(v['comparison_path']))['integrated_lufs'])
        self.assertLess(max(measured)-min(measured),.02)
        self.assertGreater(result['versions'][2]['metrics']['integrated_lufs'],result['versions'][0]['metrics']['integrated_lufs']+2)

    def test_parent_links_require_actual_output_hash(self):
        plan=self.experiment();plan['versions']=plan['versions'][:1]
        parent=master_versions(self.w,plan)
        child={**plan,'path':parent['versions'][0]['comparison_path'],'parent_event_id':parent['event_id']}
        result=master_versions(self.w,child)
        self.assertEqual(result['parent_event_id'],parent['event_id'])
        with self.assertRaises(ValueError):master_versions(self.w,{**plan,'parent_event_id':parent['event_id']})

    def test_cli_workflow_validation_is_json(self):
        (self.root/'bad.json').write_text(json.dumps({'path':'mix.wav','reverse':'yes'}))
        result=subprocess.run([shutil.which('cli-anything-ableton'),'--json','--workspace',str(self.root),'production','sample-edit','bad.json'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertFalse(json.loads(result.stdout)['ok'])

    def test_mcp_workflows_exposed_and_strict(self):
        server=create_server(workspace=self.root)
        names=[t.name for t in asyncio.run(server.list_tools())]
        self.assertEqual(len(names),22)
        for name in ['ableton_methods','ableton_reference','ableton_sample_edit','ableton_master_versions']:
            self.assertIn(name,names)
        with self.assertRaises(Exception):
            asyncio.run(server.call_tool('ableton_reference',{'plan_path':False}))
        plans={'reference.json':self.brief(),'sample.json':{'path':'mix.wav','end_seconds':.1},
               'versions.json':{**self.experiment(),'versions':[{'name':'sdk','profile':'balanced'}]}}
        for name,plan in plans.items():(self.root/name).write_text(json.dumps(plan))
        async def workflow():
            params=StdioServerParameters(command=shutil.which('ableton-mcp'),args=['--workspace',str(self.root)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    for name,args in [('ableton_methods',{'query':'effects'}),('ableton_reference',{'plan_path':'reference.json'}),
                                      ('ableton_sample_edit',{'plan_path':'sample.json'}),('ableton_master_versions',{'plan_path':'versions.json'})]:
                        result=await session.call_tool(name,args)
                        self.assertFalse(result.isError,str(result))
                    invalid=await session.call_tool('ableton_reference',{'plan_path':False})
                    self.assertTrue(invalid.isError)
        asyncio.run(workflow())


if __name__=='__main__':unittest.main()
