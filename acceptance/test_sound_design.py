import asyncio
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import soundfile as sf
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from cli_anything.ableton.production.sound_design import Design,context,render,selected_plugin
from cli_anything.ableton.production.design_worker import render_plugin
from cli_anything.ableton.production.workspace import Workspace
from cli_anything.ableton.preparation import prepare


def base():
 return {'plugin_id':'a'*20,'label':'Original acid','intent':'Short original resonant phrase','duration_seconds':1.0,'notes':[{'pitch':60,'start_seconds':.1,'duration_seconds':.3,'velocity':100}]}


class Parameter:
 type=float
 def get_raw_value_for(self,value):return float(value)/1000
 def __init__(self,plugin):self.plugin=plugin
 @property
 def raw_value(self):return self.plugin.cutoff/1000


class FakePlugin:
 is_instrument=True;preset_data=b'opaque generated state'
 def __init__(self):self.cutoff=500.0;self.parameters={'cutoff':Parameter(self)};self.calls=[]
 def __setattr__(self,key,value):
  if key=='cutoff' and (type(value) not in (int,float) or not 10<=value<=1000):raise ValueError('Range 10..1000')
  object.__setattr__(self,key,value)
 def __call__(self,midi,**kw):
  self.calls.append((midi,kw,self.cutoff))
  return np.full((2,round(kw['duration']*kw['sample_rate'])),.03,dtype=np.float32)


class SoundDesign(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ws=Workspace(self.root)
 def tearDown(self):self.tmp.cleanup()

 def test_plan_bounds_and_no_ambiguous_notes(self):
  self.assertEqual(Design.model_validate(base()).sample_rate,44100)
  for extra in [{'duration_seconds':31.0},{'sample_rate':96000},{'plugin_id':'/tmp/plugin'}, {'parameters':{'__dict__':1}}, {'parameters':{'cutoff':float('nan')}},{'parameters':{'cutoff':'NaN'}},{'parameters':{'cutoff':'-Infinity'}},{'parameters':{'cutoff':'1e9999'}},{'parameters':{f'p{i}':1 for i in range(33)}},{'automation':[{'time_seconds':1.0,'parameter':'cutoff','value':1.0}]}]:
   with self.subTest(extra=extra),self.assertRaises(ValueError):Design.model_validate({**base(),**extra})
  note=base()['notes'][0]
  with self.assertRaises(ValueError):Design.model_validate({**base(),'notes':[note,{**note,'start_seconds':.2}]})
  with self.assertRaises(ValueError):Design.model_validate({**base(),'notes':[{**note,'start_seconds':.9}]})
  with self.assertRaises(ValueError):Design.model_validate({**base(),'automation':[{'time_seconds':.2,'parameter':'cutoff','value':200.0}]*2})

 def test_worker_applies_controls_and_sorts_retriggers_without_playback(self):
  p=FakePlugin();plan=Design.model_validate({**base(),'notes':[{'pitch':60,'start_seconds':.4,'duration_seconds':.2},base()['notes'][0]],'parameters':{'cutoff':300.0},'automation':[{'time_seconds':.25,'parameter':'cutoff','value':700.0}]})
  result=render_plugin(p,plan,self.root)
  self.assertEqual(result['status'],'rendered');self.assertEqual([v['readback'] for v in result['applied_parameters']],[300.0,700.0])
  self.assertEqual([c[1]['reset'] for c in p.calls],[True,False]);self.assertTrue(all(c[1]['buffer_size']==512 for c in p.calls))
  messages=p.calls[1][0];same_time=[m[0][0]&240 for m in messages if abs(m[1]-.15)<1e-5]
  self.assertEqual(same_time,[128,144]);self.assertFalse(result['speaker_playback'])
  info=sf.info(self.root/'design.wav');self.assertEqual((info.frames,info.samplerate,info.channels),(44100,44100,2))
  self.assertEqual((self.root/'patch-start.bin').read_bytes(),p.preset_data)

 def test_unknown_parameter_and_host_range_fail_before_print(self):
  for params in [{'missing':1.0},{'cutoff':2000.0}]:
   with self.assertRaises(ValueError):render_plugin(FakePlugin(),Design.model_validate({**base(),'parameters':params}),self.root)
   self.assertFalse((self.root/'design.wav').exists())

 def test_context_is_version_matched_and_does_not_load_plugin(self):
  item={'id':'a'*20,'name':'Pigments','format':'VST3','version':'5.0.1','metadata_fingerprint':'test','offline_status':'silent_or_invalid','probe':{'status':'silent_or_invalid','parameters':['f1_cutoff_hz']},'design_evidence':{'status':'rendered','parameter_keys':['f1_resonance']}}
  data={'scanned':'now','plugins':[item]}
  with patch('cli_anything.ableton.production.sound_design.plugins.inventory',return_value=data),patch('subprocess.run',side_effect=AssertionError('No binary load')):
   out=context(self.ws,'Pigments','acid breakbeat');p=out['items'][0]
   self.assertTrue(p['version_match']);self.assertTrue(p['capabilities']);self.assertEqual(p['probe_status'],'silent_or_invalid');self.assertEqual(p['design_status'],'rendered');self.assertLessEqual(len(p['recipes']),2)
   item['version']='7.0.1';out=context(self.ws,'Pigments');self.assertFalse(out['items'][0]['version_match']);self.assertEqual(out['items'][0]['capabilities'],[])
   item['name']='Unknown';item['version']='1.0';self.assertEqual(context(self.ws,'Unknown')['items'][0]['sources'],[])
   item['name']='Pigments';item['version']='327681';self.assertFalse(context(self.ws,'Pigments')['items'][0]['version_match'])

 def test_selected_plugin_rejects_changed_external_and_vst2(self):
  path=self.root/'trusted/Plugin.vst3';path.mkdir(parents=True)
  plugin={'id':'a'*20,'path':str(path),'format':'VST3','metadata_fingerprint':'expected'}
  with patch('cli_anything.ableton.production.sound_design.plugins.inventory',return_value={'plugins':[plugin]}),patch('cli_anything.ableton.production.sound_design.plugins.ROOTS',[self.root/'trusted']),patch('cli_anything.ableton.production.sound_design.plugins.describe',return_value={'metadata_fingerprint':'different'}):
   with self.assertRaises(ValueError):selected_plugin(self.ws,'a'*20)
   plugin['path']=str(self.root)
   with self.assertRaises(ValueError):selected_plugin(self.ws,'a'*20)
   plugin['path']=str(path);plugin['format']='VST2'
   with self.assertRaises(ValueError):selected_plugin(self.ws,'a'*20)

 def run_parent(self,callback,plan=None):
  path=self.root/'plan.json';path.write_text(json.dumps(base() if plan is None else plan))
  data={'plugins':[]};plugin={'id':'a'*20,'name':'Test Instrument','version':'1.0','metadata_fingerprint':'test'};data['plugins'].append(plugin)
  with patch('cli_anything.ableton.production.sound_design.selected_plugin',return_value=(data,plugin,self.root)),patch('cli_anything.ableton.production.sound_design.subprocess.run',side_effect=callback) as run:
   result=render(self.ws,'plan.json');self.assertEqual(run.call_count,1);return result

 def test_parent_preserves_timeout_and_silent_outcomes_without_retry(self):
  def timeout(*a,**k):raise subprocess.TimeoutExpired(a[0],45)
  self.assertEqual(self.run_parent(timeout)['status'],'timeout')
  def silent(argv,**kwargs):
   (Path(argv[-1])/'design-result.json').write_text(json.dumps({'status':'silent_or_invalid'}));return SimpleNamespace(returncode=0)
  r=self.run_parent(silent);self.assertFalse(r['technical_pass']);self.assertNotIn('audio_path',r)

 def test_parent_verifies_actual_shape_and_source_hash(self):
  def good(argv,**kwargs):
   dest=Path(argv[-1]);evidence=render_plugin(FakePlugin(),Design.model_validate(base()),dest);(dest/'design-result.json').write_text(json.dumps(evidence));return SimpleNamespace(returncode=0)
  # Use a tone; constant DC cannot establish gated musical loudness reliably.
  def tone(argv,**kwargs):
   good(argv,**kwargs);t=np.arange(44100)/44100;sf.write(Path(argv[-1])/'design.wav',np.column_stack([.1*np.sin(2*np.pi*220*t)]*2),44100,subtype='FLOAT');return SimpleNamespace(returncode=0)
  r=self.run_parent(tone);self.assertTrue(r['technical_pass']);self.assertTrue(r['source_plan_preserved']);self.assertEqual(r['audio']['duration_seconds'],1)
  def wrong(argv,**kwargs):
   tone(argv,**kwargs);sf.write(Path(argv[-1])/'design.wav',np.ones((44100,1),np.float32)*.02,44100,subtype='FLOAT');return SimpleNamespace(returncode=0)
  r=self.run_parent(wrong);self.assertFalse(r['technical_pass']);self.assertEqual(r['status'],'silent_or_invalid')

 def test_nonfinite_host_conversion_is_rejected_before_any_write(self):
  p=FakePlugin();p.parameters['cutoff'].get_raw_value_for=lambda value:float('nan')
  with self.assertRaises(ValueError):render_plugin(p,Design.model_validate({**base(),'parameters':{'cutoff':300.0}}),self.root)
  self.assertEqual(p.cutoff,500.0);self.assertFalse(p.calls);self.assertFalse((self.root/'patch-start.bin').exists())

 def test_partial_failure_keeps_applied_control_and_snapshot_evidence(self):
  from cli_anything.ableton.production.design_worker import DesignFailure
  class FailsLater(FakePlugin):
   def __setattr__(self,key,value):
    if key=='cutoff' and value==700:raise RuntimeError('Selected plugin refused control')
    super().__setattr__(key,value)
  p=FailsLater();plan=Design.model_validate({**base(),'parameters':{'cutoff':300.0},'automation':[{'time_seconds':.2,'parameter':'cutoff','value':700.0}]})
  with self.assertRaises(DesignFailure) as caught:render_plugin(p,plan,self.root)
  evidence=caught.exception.evidence;self.assertEqual(evidence['applied_parameters'][0]['readback'],300)
  self.assertEqual(evidence['snapshots'][0]['file'],'patch-start.bin');self.assertFalse((self.root/'design.wav').exists())

 def test_boolean_proxy_readback_is_a_boolean(self):
  class Wrapped:
   def __init__(self,value):self.value=value
   def __bool__(self):return self.value
  class BooleanPlugin(FakePlugin):
   @property
   def enabled(self):return Wrapped(self._enabled)
   @enabled.setter
   def enabled(self,value):self._enabled=value
  p=BooleanPlugin();p.parameters['enabled']=SimpleNamespace(type=bool,raw_value=1.0,get_raw_value_for=lambda value:float(bool(value)))
  result=render_plugin(p,Design.model_validate({**base(),'parameters':{'enabled':True}}),self.root)
  self.assertIs(result['applied_parameters'][0]['readback'],True)

 def test_malformed_child_result_is_persisted_and_incomplete_evidence_warns(self):
  def malformed(argv,**kwargs):
   (Path(argv[-1])/'design-result.json').write_text('{"status":');return SimpleNamespace(returncode=0)
  r=self.run_parent(malformed);self.assertEqual(r['status'],'load_error');self.assertIn('result_sha256',r['child_result'])
  def incomplete(argv,**kwargs):
   t=np.arange(44100)/44100;sf.write(Path(argv[-1])/'design.wav',np.column_stack([.1*np.sin(2*np.pi*220*t)]*2),44100,subtype='FLOAT')
   (Path(argv[-1])/'design-result.json').write_text('{"status":"rendered"}');return SimpleNamespace(returncode=0)
  r=self.run_parent(incomplete);self.assertEqual(r['status'],'rendered');self.assertFalse(r['technical_pass']);self.assertFalse(r['patch_evidence_complete']);self.assertIn('warning',r)

 def test_malformed_nested_child_evidence_is_recorded_without_success(self):
  for overrides in [{'applied_parameters':[None]},{'snapshots':None},{'status':{'unexpected':'object'}}]:
   def malformed(argv,**kwargs):
    dest=Path(argv[-1]);t=np.arange(44100)/44100;sf.write(dest/'design.wav',np.column_stack([.1*np.sin(2*np.pi*220*t)]*2),44100,subtype='FLOAT')
    (dest/'design-result.json').write_text(json.dumps({'status':'rendered',**overrides}));return SimpleNamespace(returncode=0)
   r=self.run_parent(malformed,{**base(),'parameters':{'cutoff':300.0}});self.assertFalse(r['technical_pass']);self.assertFalse(r['patch_evidence_complete']);self.assertTrue((self.ws.path(r['output_directory'])/'report.json').is_file())

 def test_preparation_routes_sound_design_and_selects_context(self):
  r=prepare({'task':'sound_design','request':'Make acid','source':'patch.json','plugin_query':'Pigments'})
  self.assertEqual(r['next_action']['tool'],'ableton_sound_design');self.assertEqual(r['context_requests'][-1]['tool'],'ableton_plugin_context');self.assertNotIn('ableton_status',[v['tool'] for v in r['context_requests']])
  r=prepare({'task':'sound_design','request':'Make acid'},workspace_enabled=False);self.assertIsNone(r['next_action']['tool']);self.assertEqual(r['context_requests'],[])

 async def sdk(self):
  params=StdioServerParameters(command=shutil.which('ableton-mcp'),args=['--workspace',str(self.root)])
  async with stdio_client(params) as (read,write):
   async with ClientSession(read,write) as session:
    await session.initialize();names=[t.name for t in (await session.list_tools()).tools]
    self.assertIn('ableton_plugin_context',names);self.assertIn('ableton_sound_design',names);self.assertNotIn('ableton_apply',names)
    r=await session.call_tool('ableton_sound_design',{'plan_path':'missing.json'});self.assertTrue(r.isError)
    r=await session.call_tool('ableton_prepare',{'task':'sound_design','request':'Make acid','source':'patch.json','plugin_query':'Pigments'});self.assertFalse(r.isError)

 def test_official_sdk_exposes_plugin_workflow(self):asyncio.run(self.sdk())


if __name__=='__main__':unittest.main()
