"""Frozen independent black-box checks for silent review. No subjective audition."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf
from cli_anything.ableton.production.api import Production
from cli_anything.ableton.production.workspace import Workspace
from cli_anything.ableton.production.ledger import Ledger
from cli_anything.ableton.mcp_server import create_server
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class SilentListen(unittest.TestCase):
    sr = 16000

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='silent-listen-check-')
        self.root = Path(self.tmp.name)
        self.api = Production(self.root)
        t = np.arange(self.sr * 8) / self.sr
        source = np.zeros(len(t))
        lead = np.zeros(len(t))
        for start, end, freq, amp in [(2,4,220,.05),(4,6,440,.20),(6,8,880,.30)]:
            a,b=int(start*self.sr),int(end*self.sr)
            source[a:b]=amp*np.sin(2*np.pi*freq*t[a:b])
        for start, end, freq in [(2,4,440),(4,6,523.2511),(6,8,659.2551)]:
            a,b=int(start*self.sr),int(end*self.sr)
            lead[a:b]=.1*np.sin(2*np.pi*freq*t[a:b])
        sf.write(self.root/'mix.wav',np.column_stack((source,source)),self.sr,subtype='FLOAT')
        sf.write(self.root/'lead.wav',lead,self.sr,subtype='FLOAT')
        sf.write(self.root/'ref.wav',np.column_stack((source*.5,source*.5)),self.sr,subtype='FLOAT')
        self.plan={'source':'mix.wav','bpm':120,'sections':[
            {'name':'rest','start':0,'end':2},{'name':'low','start':2,'end':4},
            {'name':'middle','start':4,'end':6},{'name':'high','start':6,'end':8}],
            'stems':[{'name':'Lead','path':'lead.wav','role':'lead','monophonic':True}],
            'focus':['balance','dynamics','rhythm','melody','space','arrangement']}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, plan=None, name='plan.json'):
        (self.root/name).write_text(json.dumps(self.plan if plan is None else plan,allow_nan=False))
        return name

    def run_plan(self,plan=None):
        return self.api.listen(self.save(plan))

    def test_sections_preservation_provenance_and_review(self):
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.wav')}
        result=self.run_plan()
        self.assertEqual(result['source']['sha256'],before['mix.wav'])
        self.assertEqual(result['source']['duration_seconds'],8)
        self.assertEqual(len(result['timeline']),4)
        rest,low,middle,high=result['timeline']
        self.assertTrue(rest['silent'])
        self.assertEqual((rest['start_seconds'],rest['end_seconds']),(0,2))
        self.assertGreater(middle['rms_dbfs']-low['rms_dbfs'],10)
        self.assertGreater(high['spectral_centroid_hz'],middle['spectral_centroid_hz']*1.5)
        self.assertGreater(middle['spectral_centroid_hz'],low['spectral_centroid_hz']*1.5)
        self.assertEqual(result['review']['creative_acceptance'],'pending')
        self.assertIs(result['review']['perceptual_listening'],False)
        self.assertIs(result['review']['speaker_playback'],False)
        self.assertIsInstance(result['observations'],list)
        self.assertIsInstance(result['proposed_actions'],list)
        self.assertNotIn('quality_score',result)
        encoded=json.dumps(result,allow_nan=False)
        self.assertLess(len(encoded.encode()),256*1024)
        saved=self.root/result['report_path']
        self.assertTrue(saved.is_file())
        json.dumps(json.loads(saved.read_text()),allow_nan=False)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.wav')})
        events=Ledger(Workspace(self.root)).recall()['events']
        self.assertTrue(any(e['id']==result['event_id'] and e['kind']=='review' for e in events))
        second=self.run_plan()
        self.assertNotEqual(result['report_path'],second['report_path'])
        job=self.api.progress(result['progress_job_id'])
        self.assertIn('completed',str(job))

    def test_monophonic_note_contour_rests_and_confidence(self):
        result=self.run_plan()
        stem=result['stems'][0]
        self.assertEqual(stem['sha256'],hashlib.sha256((self.root/'lead.wav').read_bytes()).hexdigest())
        pitch=stem['pitch']
        self.assertGreater(pitch['voiced_fraction'],.60)
        self.assertLess(pitch['voiced_fraction'],.82)
        self.assertLessEqual(len(pitch['events']),128)
        self.assertTrue(pitch['limits'])
        events=pitch['events']
        self.assertTrue(events)
        self.assertGreaterEqual(min(e['start_seconds'] for e in events),1.8)
        for midpoint,wanted in [(3,69),(5,72),(7,76)]:
            matches=[e for e in events if e['start_seconds']<=midpoint<=e['end_seconds']]
            self.assertTrue(matches,(midpoint,events))
            self.assertLessEqual(abs(matches[0]['midi']-wanted),1)
            self.assertGreater(matches[0]['confidence'],.6)
        # A full mix and unasserted/polyphonic stems must not be promoted into melody evidence.
        p=dict(self.plan);p['stems']=[{'name':'Lead','path':'lead.wav','role':'lead'}]
        other=self.run_plan(p)
        self.assertFalse(other['stems'][0].get('pitch'))
        self.assertNotIn('pitch',other['source'])

    def test_rhythm_matches_explicit_grid_not_inferred_tempo(self):
        x=np.zeros(self.sr*8)
        for time in np.arange(.5,8,.5):
            start=int(time*self.sr)
            n=np.arange(400)
            x[start:start+400]+=.5*np.exp(-n/60)*np.sin(2*np.pi*1000*n/self.sr)
        sf.write(self.root/'pulses.wav',x,self.sr,subtype='FLOAT')
        p={'source':'pulses.wav','bpm':120}
        r=self.run_plan(p)
        window=r['timeline'][0]
        self.assertGreaterEqual(window['onset_count'],10)
        self.assertEqual(window['rhythm']['bpm_hint'],120)
        self.assertEqual(window['rhythm']['grid'],'sixteenth_from_time_zero')
        self.assertLess(window['rhythm']['median_grid_error_ms'],40)
        self.assertNotIn('estimated_bpm',r)
        self.assertEqual(len(r['timeline']),1)

    def test_reference_is_diagnostic_level_match(self):
        p=dict(self.plan);p['reference']='ref.wav'
        r=self.run_plan(p)
        self.assertTrue(r['reference'])
        self.assertNotIn('prefer',str(r['review']).lower())
        self.assertIn('level',str(r['reference']).lower())
        self.assertIn(hashlib.sha256((self.root/'ref.wav').read_bytes()).hexdigest(),json.dumps(r['reference']))

    def test_invalid_schema_paths_sections_and_alignment(self):
        bad=[]
        for key,val in [('unknown',1),('bpm',True),('bpm',39),('bpm',241),('focus',['invented'])]:
            p=dict(self.plan);p[key]=val;bad.append(p)
        bad.extend([
            {'source':'mix.wav','sections':[{'name':'b','start':2,'end':4},{'name':'a','start':1,'end':3}]},
            {'source':'mix.wav','sections':[{'name':'overflow','start':0,'end':9}]},
            {'source':'mix.wav','sections':[{'name':'bool','start':False,'end':2}]},
            {'source':'mix.wav','stems':[{'name':'x','path':'lead.wav','role':'kick','monophonic':True}]},
            {'source':'../escape.wav'},
        ])
        with tempfile.TemporaryDirectory() as outside:
            ext=Path(outside)/'outside.wav';shutil.copyfile(self.root/'mix.wav',ext)
            (self.root/'escape.wav').symlink_to(ext)
            bad.append({'source':'mix.wav','reference':'escape.wav'})
            sf.write(self.root/'short.wav',np.ones(self.sr)*.01,self.sr)
            bad.append({'source':'mix.wav','stems':[{'name':'x','path':'short.wav','role':'lead','monophonic':True}]})
            sf.write(self.root/'wrong-rate.wav',np.ones(self.sr*8)*.01,8000)
            bad.append({'source':'mix.wav','stems':[{'name':'x','path':'wrong-rate.wav','role':'other'}]})
            for p in bad:
                with self.subTest(plan=p), self.assertRaises((ValueError,FileNotFoundError,TypeError)):
                    self.run_plan(p)
        reviews=[e for e in Ledger(Workspace(self.root)).recall()['events'] if e['kind']=='review']
        self.assertFalse(reviews)

    def test_cli_workspace_contract(self):
        script=Path(sys.executable).parent/'cli-anything-ableton'
        args=[str(script),'--json','--workspace',str(self.root),'production','listen',self.save()]
        proc=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertFalse(json.loads(proc.stdout)['review']['speaker_playback'])
        absent=subprocess.run([str(script),'--json','production','listen','plan.json'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(absent.returncode,0)

    def test_mcp_workspace_exposure_and_round_trip(self):
        asyncio.run(self._mcp())

    async def _mcp(self):
        # A no-workspace server cannot expose the mode, and none of these calls should reach Live.
        class Backend:
            def call(self,*args,**kwargs):
                raise AssertionError('Silent review reached Live backend')
        server=create_server(client=Backend())
        self.assertNotIn('ableton_listen',[t.name for t in await server.list_tools()])
        params=StdioServerParameters(command=str(Path(sys.executable).parent/'ableton-mcp'),args=['--workspace',str(self.root)])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                self.assertIn('ableton_listen',[t.name for t in (await session.list_tools()).tools])
                report=await session.call_tool('ableton_listen',{'plan_path':self.save()})
                self.assertFalse(report.isError,str(report))
                self.assertFalse(json.loads(report.content[0].text)['review']['speaker_playback'])
                bad=await session.call_tool('ableton_listen',{'plan_path':'plan.json','unknown':True})
                self.assertTrue(bad.isError)


if __name__=='__main__':
    unittest.main(verbosity=2)
