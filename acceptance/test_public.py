"""Release boundaries: exported bytes, portable docs and playable MIDI structure."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
import hashlib
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def number(data, pos):
    value=0
    for _ in range(4):
        item=data[pos];pos+=1;value=(value<<7)|(item&127)
        if item<128:return value,pos
    raise AssertionError('Invalid MIDI variable-length quantity')


class PublicRelease(unittest.TestCase):
    def test_standard_midi_timing_channels_and_no_stuck_notes(self):
        demo=module('demo_songs')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'song.mid'
            demo.write_midi(p,{'Kick':[[0,36,.15,110],[3.5,36,.2,100]],'Hook':[[.75,69,1.2,90],[3.9,72,.5,70]]},128,4)
            raw=p.read_bytes();self.assertEqual(raw[:4],b'MThd')
            size,fmt,count,ticks=struct.unpack('>IHHH',raw[4:14]);self.assertEqual((size,fmt,count,ticks),(6,1,3,960))
            pos=14;note_on=0;tempos=[]
            for _ in range(count):
                self.assertEqual(raw[pos:pos+4],b'MTrk');length=int.from_bytes(raw[pos+4:pos+8],'big')
                chunk=raw[pos+8:pos+8+length];pos+=8+length;at=0;tick=0;held=set();ended=False
                while at<len(chunk):
                    delta,at=number(chunk,at);tick+=delta;status=chunk[at];at+=1
                    if status==255:
                        kind=chunk[at];at+=1;length,at=number(chunk,at);value=chunk[at:at+length];at+=length
                        if kind==81:tempos.append(int.from_bytes(value,'big'))
                        if kind==47:ended=True;self.assertEqual(tick,3840)
                    else:
                        pitch,velocity=chunk[at:at+2];at+=2;key=(status&15,pitch)
                        if status&240==144 and velocity:
                            self.assertNotIn(key,held);held.add(key);note_on+=1
                        else:self.assertIn(key,held);held.remove(key)
                    self.assertLessEqual(tick,3840)
                self.assertTrue(ended);self.assertFalse(held)
            self.assertEqual(note_on,4);self.assertEqual(tempos,[468750]);self.assertEqual(pos,len(raw))

    def test_recipes_have_distinct_full_length_section_maps(self):
        demo=module('demo_songs');a=demo.recipe('horizon');b=demo.recipe('pulse')
        self.assertNotEqual(a['seed'],b['seed']);self.assertNotEqual(a['bpm'],b['bpm'])
        for data in (a,b):
            self.assertEqual(data['bars']*240/data['bpm'],120)
            starts=[s[0] for s in data['sections']]
            self.assertEqual(starts[0],0);self.assertEqual(starts,sorted(set(starts)))
            self.assertGreaterEqual(len(starts),6);self.assertLess(starts[-1],data['bars'])
        self.assertEqual(len(demo.ROLES),10)
        with self.assertRaises(ValueError):demo.recipe('unknown')

    def test_export_excludes_runtime_and_private_history_and_matches_manifest(self):
        exporter=module('export_public')
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'public';result=exporter.export(destination)
            manifest=json.loads((destination/'PUBLIC-MANIFEST.json').read_text())['sha256']
            self.assertEqual(result['files'],len(manifest)+1)
            for relative,sha in manifest.items():
                path=Path(relative)
                self.assertFalse(set(path.parts)&{'.git','.runtime','.proof','.venv','.ableton-harness','production-workspace'})
                self.assertNotIn(path.suffix.lower(),{'.wav','.flac','.mp3','.mid','.sqlite','.vst3','.als'})
                self.assertNotEqual(path.name,'bridge.json');self.assertNotEqual(relative,'mcp-config.json')
                data=(destination/path).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),sha)
                self.assertNotIn(bytes([47])+b'Users'+bytes([47]),data,relative)
            self.assertTrue((destination/'LICENSE').is_file());self.assertTrue((destination/'licenses/CLI-Anything-Apache-2.0.txt').is_file())
            self.assertFalse((destination/'docs/WORKLOG.md').exists())
            self.assertNotIn('this Mac', (destination/'README.md').read_text())
            self.assertIn('ABSOLUTE/PATH',(destination/'mcp-config.example.json').read_text())

    def test_injected_private_assets_are_not_exported(self):
        exporter=module('export_public')
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'source';fixture.mkdir()
            for relative in exporter.FILES:
                target=fixture/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,target)
            for relative in ['examples/private.wav','examples/bridge.json','acceptance/local-notes.txt']:
                (fixture/relative).write_text('PRIVATE SENTINEL')
            with patch.object(exporter,'ROOT',fixture):
                destination=Path(tmp)/'public';exporter.export(destination)
            for relative in ['examples/private.wav','examples/bridge.json','acceptance/local-notes.txt']:
                self.assertFalse((destination/relative).exists())
            package=(destination/'cli_anything/ableton/README.md').read_text()
            for target in re.findall(r'\]\(([^)]+)\)',package):
                self.assertTrue('://' in target or target.startswith('#'),target)

    def test_export_never_overwrites_nonempty_destination(self):
        exporter=module('export_public')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'keep.txt';p.write_text('original')
            with self.assertRaises(ValueError):exporter.export(Path(tmp))
            self.assertEqual(p.read_text(),'original')

    def test_user_guide_local_links_and_capability_boundaries(self):
        text=(ROOT/'USER_GUIDE.md').read_text()
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if '://' not in target and not target.startswith('#'):
                self.assertTrue((ROOT/target.split('#')[0]).is_file(),target)
        self.assertIn('20 tools',text);self.assertIn('not a general composition endpoint',text)
        self.assertIn('No speakers',text);self.assertIn('Native editing is opt-in',text)
        self.assertIn('not model training',text);self.assertIn('perceptual',text)


if __name__=='__main__':unittest.main()
