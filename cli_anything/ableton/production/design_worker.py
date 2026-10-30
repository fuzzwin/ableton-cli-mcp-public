"""Explicit child-only instrument render. No UI, output device or state import."""
import json
import hashlib
import math
from pathlib import Path
import sys


class DesignFailure(ValueError):
    def __init__(self,message,evidence):
        super().__init__(message);self.evidence=evidence


def render_plugin(plugin,plan,destination):
    import numpy as np
    import soundfile as sf
    if not plugin.is_instrument:raise ValueError('Sound design currently requires an instrument plugin')
    parameters=plugin.parameters  # Initialize/enumerate before processing; retain exact host names.
    requested=set(plan.parameters)|{p.parameter for p in plan.automation}
    if not requested<=set(parameters):raise ValueError('Unknown plugin parameter: '+','.join(sorted(requested-set(parameters))))
    audit=[]
    # Prevalidate every requested value before the first native control write.
    for key,value in list(plan.parameters.items())+[(c.parameter,c.value) for c in plan.automation]:
        raw=float(parameters[key].get_raw_value_for(value))
        if not math.isfinite(raw) or not 0<=raw<=1:raise ValueError('Invalid normalized control value: '+key)
    def change(key,value,at):
        parameter=parameters[key]
        # Pedalboard validates actual-unit numeric range or enum choices; no clamping/guessing.
        setattr(plugin,key,value)
        actual=getattr(plugin,key)
        raw=float(parameter.raw_value)
        if not math.isfinite(raw):raise ValueError('Plugin returned nonfinite control state')
        readback=bool(actual) if parameter.type is bool else float(actual) if parameter.type is float else str(actual)
        audit.append({'time_seconds':at,'parameter':key,'requested':value,'readback':readback,'normalized':raw})
    snapshots=[]
    try:
        for key,value in plan.parameters.items():change(key,value,0)
        def snapshot(name):
            try:
                blob=plugin.preset_data
                if len(blob)>32*1024*1024:raise ValueError('Plugin state exceeds 32 MiB')
                p=destination/name;p.write_bytes(blob);snapshots.append({'file':name,'sha256':hashlib.sha256(blob).hexdigest()})
            except (AttributeError,RuntimeError,ValueError) as exc:
                snapshots.append({'unavailable':str(exc)[:300]})
        snapshot('patch-start.bin')
        sr=plan.sample_rate;frames=round(plan.duration_seconds*sr)
        timeline=[]
        for note in plan.notes:
            timeline.extend([(round(note.start_seconds*sr),1,bytes([0x90|note.channel,note.pitch,note.velocity])),
                             (round((note.start_seconds+note.duration_seconds)*sr),0,bytes([0x80|note.channel,note.pitch,0]))])
        timeline.sort(key=lambda e:(e[0],e[1]))
        changes={}
        for c in sorted(plan.automation,key=lambda c:c.time_seconds):changes.setdefault(round(c.time_seconds*sr),[]).append(c)
        boundaries=sorted({0,frames}|set(changes));x=np.zeros((2,frames),np.float32);cursor=0
        for index,(start,end) in enumerate(zip(boundaries,boundaries[1:])):
            for c in changes.get(start,[]):change(c.parameter,c.value,c.time_seconds)
            midi=[]
            while cursor<len(timeline) and timeline[cursor][0]<end:
                frame,_,message=timeline[cursor];midi.append((message,(frame-start)/sr));cursor+=1
            y=plugin(midi,duration=(end-start)/sr,sample_rate=sr,num_channels=2,buffer_size=512,reset=index==0)
            if y.shape!=(2,end-start) or not np.isfinite(y).all():raise ValueError('Plugin returned invalid shape or nonfinite audio')
            x[:,start:end]=y
        peak=float(np.max(abs(x)))
        result={'status':'rendered' if peak>1e-6 else 'silent_or_invalid','peak':peak,'finite':True,'frames':frames,'sample_rate':sr,
                'buffer_size':512,'parameter_count':len(parameters),'applied_parameters':audit,'parameter_keys':sorted(requested),
                'snapshots':snapshots,'speaker_playback':False,'midi_note_count':len(plan.notes),'sorted_midi':True}
        snapshot('patch-end.bin')
        if peak>1e-6:sf.write(destination/'design.wav',x.T,sr,subtype='FLOAT')
        return result
    except Exception as exc:
        raise DesignFailure(str(exc),{"applied_parameters":audit,"snapshots":snapshots,"speaker_playback":False}) from exc


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(35,35))
    from pedalboard import load_plugin
    from .sound_design import Design
    destination=Path(sys.argv[2])
    try:
        plan=Design.model_validate_json((destination/'design-plan.json').read_text())
        plugin=load_plugin(sys.argv[1],initialization_timeout=10)
        result=render_plugin(plugin,plan,destination)
    except DesignFailure as exc:result={'status':'load_error','reason':str(exc)[:2000],'partial_evidence':exc.evidence,'speaker_playback':False}
    except Exception as exc:result={'status':'load_error','reason':str(exc)[:2000],'speaker_playback':False}
    (destination/'design-result.json').write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
