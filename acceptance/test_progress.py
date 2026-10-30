import asyncio
import copy
import concurrent.futures
import json
import plistlib
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from cli_anything.ableton.production.api import Production
from cli_anything.ableton.production.workspace import Workspace, digest
from cli_anything.ableton.production.progress import Job, checkpoint, observe, read_jobs
from cli_anything.ableton.production import plugins


class Progress(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.w=Workspace(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def audio(self):
        t=np.arange(32000)/16000
        x=np.column_stack([.1*np.sin(2*np.pi*180*t)]*2)
        sf.write(self.root/'mix.wav',x,16000,subtype='FLOAT')

    def test_empty_status_creates_nothing(self):
        self.assertEqual(read_jobs(self.w)['jobs'],[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_actual_stage_order_and_item_counts(self):
        notifications=[]
        with observe(notifications.append):
            with Job(self.w,'mix') as job:
                checkpoint('mix','Processing',1,3)
                snapshot=read_jobs(self.w,job.id)['jobs'][0]
                self.assertEqual(snapshot['stages'][0]['state'],'complete')
                self.assertEqual(snapshot['stages'][1]['state'],'running')
                self.assertEqual(snapshot['items'],{'completed':1,'total':3})
                self.assertEqual(snapshot['stages'][-1]['state'],'queued')
                for stage in ['master','write','checks','record']:checkpoint(stage)
                job.outcome({'event_id':'test'})
        final=read_jobs(self.w,job.id)['jobs'][0]
        self.assertEqual(final['state'],'completed')
        self.assertEqual(final['completed_stages'],6)
        self.assertTrue(all(a['sequence']<b['sequence'] for a,b in zip(notifications,notifications[1:])))
        with self.assertRaises(ValueError):job.advance('record')

    def test_failure_keeps_completed_and_queued_stages(self):
        with self.assertRaisesRegex(ValueError,'bad source'):
            with Job(self.w,'master') as job:
                checkpoint('master')
                raise ValueError('bad source')
        final=read_jobs(self.w,job.id)['jobs'][0]
        self.assertEqual(final['state'],'failed')
        self.assertEqual([s['state'] for s in final['stages']],['complete','failed','queued','queued','queued'])
        self.assertIn('bad source',final['error'])

    def test_unreached_stages_never_claim_completion(self):
        with Job(self.w,'master') as job:job.outcome({})
        final=read_jobs(self.w,job.id)['jobs'][0]
        self.assertEqual(final['state'],'unconfirmed')
        self.assertEqual(final['completed_stages'],1)

    def test_stale_heartbeat_is_unconfirmed_and_read_only(self):
        with Job(self.w,'inventory') as job:
            saved=json.loads(job.path.read_text());saved['heartbeat_epoch']=0
            job.path.write_text(json.dumps(saved))
            before=digest(job.path)
            result=read_jobs(self.w,job.id,now=30)['jobs'][0]
            self.assertEqual(result['state'],'unconfirmed')
            self.assertEqual(digest(job.path),before)
            checkpoint('inventory')
            job.outcome({})

    def test_heartbeat_adds_no_fake_stage_events(self):
        with Job(self.w,'inventory',heartbeat_seconds=.02) as job:
            before=json.loads(job.path.read_text())
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                threading.Event().wait(.02)
                after=json.loads(job.path.read_text())
                if after['heartbeat_epoch']>before['heartbeat_epoch']:break
            self.assertGreater(after['heartbeat_epoch'],before['heartbeat_epoch'])
            self.assertEqual(after['events'],before['events'])
            self.assertEqual(after['completed_stages'],before['completed_stages'])
            checkpoint('inventory');job.outcome({})
        before=digest(job.path);threading.Event().wait(.06)
        self.assertEqual(digest(job.path),before)

    def test_concurrent_jobs_remain_separate(self):
        barrier=threading.Barrier(2)
        def work():
            with Job(self.w,'inventory') as job:
                barrier.wait(timeout=3)
                checkpoint('inventory');job.outcome({})
            return job.id
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(lambda _:work(),range(2)))
        self.assertEqual(len(set(ids)),2)
        self.assertEqual({j['job_id'] for j in read_jobs(self.w)['jobs']},set(ids))
        self.assertTrue(all(j['state']=='completed' for j in read_jobs(self.w)['jobs']))

    def test_invalid_id_and_escaping_directory_rejected(self):
        with self.assertRaises(ValueError):read_jobs(self.w,'../escape')
        state=self.w.state_dir()
        (state/'jobs').symlink_to('/private/tmp',target_is_directory=True)
        with self.assertRaises(ValueError):read_jobs(self.w)
        with self.assertRaises(ValueError):Job(self.w,'master')

    def test_malformed_records_never_claim_liveness_or_completion(self):
        with Job(self.w,'inventory') as job:
            checkpoint('inventory');job.outcome({})
        valid=json.loads(job.path.read_text())
        cases=[{'heartbeat_epoch':float('nan'),'state':'running'},
               {'heartbeat_epoch':0,'state':'completed'},
               {**valid,'state':None}, {**valid,'heartbeat_epoch':float('nan')},
               {**valid,'completed_stages':0}, {**valid,'job_id':'wrong'},
               {**valid,'unexpected':float('nan')}, {**valid,'unexpected':float('inf')}]
        for data in cases:
            job.path.write_text(json.dumps(data))
            self.assertEqual(read_jobs(self.w,job.id)['jobs'][0]['state'],'unconfirmed')
        future=copy.deepcopy(valid);future['state']='running';future['stages'][-1]['state']='running';future['completed_stages']=1
        job.path.write_text(json.dumps(future))
        self.assertEqual(read_jobs(self.w,job.id,now=0)['jobs'][0]['state'],'unconfirmed')

    def test_mcp_worker_limit_keeps_status_responsive(self):
        from cli_anything.ableton.mcp_server import create_server
        release=threading.Event();lock=threading.Lock();counts={'active':0,'peak':0,'started':0}
        def blocked_master(self,*args):
            with lock:
                counts['active']+=1;counts['started']+=1;counts['peak']=max(counts['peak'],counts['active'])
            try:
                if not release.wait(5):raise RuntimeError('Test worker wait expired')
                return {'test':True}
            finally:
                with lock:counts['active']-=1
        async def exercise():
            server=create_server(workspace=self.root)
            tasks=[asyncio.create_task(server.call_tool('ableton_master',{'path':'unused.wav'})) for _ in range(3)]
            try:
                deadline=time.monotonic()+3
                while counts['started']<2 and time.monotonic()<deadline:await asyncio.sleep(.01)
                await asyncio.sleep(.03)
                self.assertEqual(counts['started'],2)
                await asyncio.wait_for(server.call_tool('ableton_progress',{}),timeout=1)
            finally:
                release.set()
                await asyncio.gather(*tasks)
        with patch.object(Production,'master',blocked_master):asyncio.run(exercise())
        self.assertEqual(counts['peak'],2)

    def test_observer_failure_does_not_corrupt_render(self):
        self.audio()
        def failed(_):raise RuntimeError('Disconnected UI')
        with observe(failed):result=Production(self.root).master('mix.wav')
        job=read_jobs(self.w,result['progress_job_id'])['jobs'][0]
        self.assertGreater(job['observer_errors'],0)
        self.assertIn(job['state'],['completed','needs_attention'])
        self.assertTrue(self.w.path(result['output_directory']+'/master.wav').exists())

    def test_real_workflow_stages_and_failed_input(self):
        self.audio();p=Production(self.root)
        plans={'mix.json':{'stems':[{'path':'mix.wav','role':'kick'}]},
               'sample.json':{'path':'mix.wav','end_seconds':.1},
               'reference.json':{'label':'test','reference':{'path':'mix.wav'},'focus':['bass']},
               'versions.json':{'path':'mix.wav','intent':'test','versions':[{'name':'a','profile':'balanced'}]}}
        for name,data in plans.items():(self.root/name).write_text(json.dumps(data))
        results=[p.analyze('mix.wav'),p.mix('mix.json'),p.sample_edit('sample.json'),p.reference('reference.json'),p.master_versions('versions.json')]
        for result in results:
            job=read_jobs(self.w,result['progress_job_id'])['jobs'][0]
            self.assertIn(job['state'],['completed','needs_attention'])
            self.assertEqual(job['completed_stages'],job['total_stages'])
        with self.assertRaises(OSError):p.master('missing.wav')
        self.assertEqual(read_jobs(self.w)['jobs'][0]['state'],'failed')

    def test_failed_plugin_outcome_needs_attention(self):
        root=self.root/'plugins';bundle=root/'Broken.vst3/Contents';bundle.mkdir(parents=True)
        (bundle/'Info.plist').write_bytes(plistlib.dumps({'CFBundleName':'Broken'}))
        p=Production(self.root)
        with patch.object(plugins,'ROOTS',[root]):
            inventory=p.inventory(refresh=True)
            result=p.probe(inventory['items'][0]['id'])
        job=read_jobs(self.w,result['progress_job_id'])['jobs'][0]
        self.assertEqual(result['status'],'load_error')
        self.assertEqual(job['state'],'needs_attention')

    async def sdk(self):
        params=StdioServerParameters(command=shutil.which('ableton-mcp'),args=['--workspace',str(self.root)])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                notifications=[]
                async def progress(value,total,message):notifications.append((value,total,message))
                result=await session.call_tool('ableton_master',{'path':'mix.wav'},progress_callback=progress)
                self.assertFalse(result.isError,str(result))
                output=json.loads(result.content[0].text)
                self.assertGreater(len(notifications),3)
                self.assertTrue(all(a[0]<b[0] for a,b in zip(notifications,notifications[1:])))
                self.assertTrue(all(n[1] is None and 'stages' in n[2] for n in notifications))
                state=await session.call_tool('ableton_progress',{'job_id':output['progress_job_id']})
                self.assertFalse(state.isError)
                job=json.loads(state.content[0].text)['jobs'][0]
                self.assertEqual(job['observer_errors'],0)
                self.assertIn(job['state'],['completed','needs_attention'])

    def test_official_sdk_progress_and_status(self):
        self.audio();asyncio.run(self.sdk())


if __name__=='__main__':unittest.main()
