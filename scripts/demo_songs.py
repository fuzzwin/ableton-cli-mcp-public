"""Two original, reproducible, file-only demo recipes; no commercial samples.

Run from a source checkout: python scripts/demo_songs.py --workspace /path/to/work
This is an authored example, not a general composition MCP endpoint. No playback.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RECIPES = {
    "horizon": {"title": "Horizon After Rain", "bpm": 128, "bars": 64, "seed": 128640,
                "key": "F sharp minor", "direction": "Spacious melodic house: suspended harmony, analog motion, deep mono bass, a long emotional build.",
                "sections": [(0,"First light"),(8,"Forward motion"),(16,"Open sky"),(32,"Weightless"),(40,"The climb"),(48,"After rain"),(60,"Last light")]},
    "pulse": {"title": "Signal in the Concrete", "bpm": 136, "bars": 68, "seed": 136680,
              "key": "D minor", "direction": "Intimate chopped synth gestures, swung broken beats, a halftime bass turn, acid sequences and a big-beat final lift.",
              "sections": [(0,"Voice of the circuit"),(8,"Street pulse"),(24,"Half time"),(32,"Pressure rising"),(40,"Collision"),(56,"Acid orbit"),(64,"Afterimage")]},
}
ROLES = {"01 Kick":"kick", "02 Snare":"drums", "03 Hats":"drums", "04 Percussion":"drums",
         "05 Deep Sub":"sub", "06 Moving Bass":"bass", "07 Chords":"pad", "08 Hook":"lead",
         "09 Atmosphere":"pad", "10 Transitions":"fx"}
PEAKS = [.62,.23,.10,.12,.26,.19,.18,.18,.07,.11]


def recipe(name):
    if name not in RECIPES:
        raise ValueError("Choose horizon or pulse")
    data = RECIPES[name]
    assert data["bars"] * 4 * 60 / data["bpm"] == 120
    return data


def vlq(number):
    values = [int(number) & 127]
    number >>= 7
    while number:
        values.insert(0, (number & 127) | 128)
        number >>= 7
    return bytes(values)


def write_midi(path, notes, bpm, beats):
    """Standard MIDI format 1, conductor plus ten editable instrument tracks."""
    ticks = 960
    tempo = round(60_000_000 / bpm)
    conductor = b'\x00\xff\x51\x03' + tempo.to_bytes(3,'big') + b'\x00\xff\x58\x04\x04\x02\x18\x08'
    conductor += vlq(round(beats*ticks)) + b'\xff\x2f\x00'
    chunks = [conductor]
    for index, (name, events) in enumerate(notes.items()):
        channel = 9 if index < 4 else index - 4
        timeline = []
        for beat, pitch, duration, velocity in events:
            start = round(max(0,beat)*ticks)
            stop = min(round(beats*ticks), round((beat+duration)*ticks))
            if stop <= start:
                continue
            timeline.extend([(start,1,bytes([0x90|channel,pitch,velocity])),(stop,0,bytes([0x80|channel,pitch,0]))])
        label = name.encode('ascii')
        data = b'\x00\xff\x03' + vlq(len(label)) + label
        last = 0
        for tick, _, message in sorted(timeline):
            data += vlq(tick-last) + message
            last = tick
        data += vlq(round(beats*ticks)-last) + b'\xff\x2f\x00'
        chunks.append(data)
    path.write_bytes(b'MThd'+struct.pack('>IHHH',6,1,len(chunks),ticks)+b''.join(b'MTrk'+struct.pack('>I',len(c))+c for c in chunks))


def compose(workspace, name, *, sr=44100):
    import numpy as np
    import soundfile as sf
    from scipy.signal import butter, sosfilt
    from pedalboard import Pedalboard, Reverb, Chorus
    from cli_anything.ableton.production.workspace import Workspace, digest

    config = recipe(name)
    ws = Workspace(workspace)
    destination = ws.root / (name+'-'+uuid.uuid4().hex[:12])
    destination.mkdir(exist_ok=False)
    stems = destination / 'stems'
    stems.mkdir()
    bpm = config['bpm']; spb = 60/bpm; total = round(120*sr)
    rng = np.random.default_rng(config['seed'])
    notes = {key:[] for key in ROLES}
    paths = []
    kicks = []
    roots = [30,26,33,28] if name == 'horizon' else [26,26,29,24]
    voicings = [[54,57,61,64,68],[50,54,57,61,64],[57,61,64,68,71],[52,56,59,62,66]] if name == 'horizon' else [[50,53,57,60],[50,53,57,64],[53,57,60,65],[48,52,55,62]]

    def filt(x, hz, kind='lowpass'):
        return sosfilt(butter(2,hz,btype=kind,fs=sr,output='sos'),x,axis=0).astype(np.float32)

    def envelope(t, length, attack=.008, release=.08):
        return np.minimum(1,t/attack)*np.clip((length-t)/release,0,1)

    @lru_cache(maxsize=256)
    def tone(pitch, duration, mode):
        f=440*2**((pitch-69)/12)
        seconds=duration*spb + (.55 if mode=='pad' else .15)
        t=np.arange(round(seconds*sr))/sr
        gate=envelope(t,seconds,.19 if mode=='pad' else .004,.55 if mode=='pad' else .10)
        if mode=='sub':
            mono=(np.sin(2*np.pi*f*t)+.075*np.sin(4*np.pi*f*t))*gate
            return mono.astype(np.float32)
        if mode in ('pluck','chop','bell'):
            carrier=np.sin(2*np.pi*f*t+np.sin(2*np.pi*f*2.003*t)*(2.8 if mode=='bell' else 1.8)*np.exp(-t/.11))
            mono=carrier*np.exp(-t/(.24 if mode=='chop' else .55))*gate
            if mode=='chop':
                # A synthesized vowel-like band balance; no voice/recording is used.
                mono=filt(mono,2800)+.26*np.sin(2*np.pi*f*3*t)*np.exp(-t/.09)*gate
            return mono.astype(np.float32)
        voices=[]
        for cents in ([-5,5] if mode=='pad' else [-3,3]):
            detune=2**(cents/1200)
            wave=np.zeros(len(t))
            for harmonic in range(1, min(20, int(sr*.43/(f*detune)))+1):
                weight=(1/harmonic**1.65) if mode=='pad' else (1/harmonic**1.1)
                wave+=weight*np.sin(2*np.pi*f*detune*harmonic*t+.1*harmonic)
            wave=filt(wave,1800 if mode=='pad' else 360+(pitch%7)*330)
            wave*=gate*(1 if mode=='pad' else np.exp(-t/.20))
            voices.append(wave)
        return np.stack(voices,axis=1).astype(np.float32)*.6

    def add(buffer, sample, beat, gain=1, pan=0):
        start=round(beat*spb*sr)
        if start>=total or start<0:return
        if sample.ndim==1:
            sample=sample[:,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],dtype=np.float32)
        length=min(len(sample),total-start)
        buffer[start:start+length]+=sample[:length]*gain

    def hit(buffer, track, beat, pitch, duration, velocity, mode, pan=0):
        duration=round(duration,3)
        add(buffer,tone(pitch,duration,mode),beat,velocity/127,pan)
        notes[track].append([round(beat,6),pitch,duration,velocity])

    def active(bar):
        return (8<=bar<32 or 44<=bar<60) if name=='horizon' else (4<=bar<32 or 36<=bar<64)

    for bar in range(config['bars']):
        if not active(bar):continue
        if name=='horizon':positions=[0,1,2,3]
        elif 24<=bar<32:positions=[0,2.75]
        elif 40<=bar<64:positions=[0,1,2,3] if bar%4<2 else [0,.75,1.5,2.5,3.25]
        else:positions=[0,1.5,2.5,3.5] if bar%2 else [0,.75,2,2.75]
        if bar in (31,47,59,63):positions=positions[:-1]
        kicks.extend([bar*4+p for p in positions])
    duck=np.ones(total,dtype=np.float32)
    for beat in kicks:
        pos=round(beat*spb*sr);length=min(round(.35*sr),total-pos)
        t=np.arange(length)/sr
        duck[pos:pos+length]=np.minimum(duck[pos:pos+length],1-.90*np.exp(-t/.075))

    def delay(x, amount, beat=.75):
        out=x.copy()
        for repeat in range(1,5):
            shift=round(beat*spb*sr*repeat)
            out[shift:]+=x[:-shift,::-1]*(amount*.5**(repeat-1))
        return out

    # Original one-shots. No sample packs, VSTs, voices or copyrighted recordings.
    t=np.arange(round(.45*sr))/sr
    freq=(46 if name=='horizon' else 49)+100*np.exp(-t/.021)+145*np.exp(-t/.003)
    kick=np.tanh(1.5*np.sin(2*np.pi*np.cumsum(freq)/sr))*np.exp(-t/.115)*envelope(t,.45,.001,.06)
    clap_t=np.arange(round(.25*sr))/sr
    noise=filt(rng.normal(0,1,len(clap_t)),[900,10000],'bandpass')
    clap=noise*(np.exp(-clap_t/.065)+.5*np.exp(-((clap_t-.018)/.006)**2)+.4*np.exp(-((clap_t-.031)/.006)**2))
    snare=clap+.35*np.sin(2*np.pi*190*clap_t)*np.exp(-clap_t/.05)
    hat_t=np.arange(round(.13*sr))/sr
    hat=filt(rng.normal(0,1,len(hat_t)),[6500,16000],'bandpass')*np.exp(-hat_t/.022)*envelope(hat_t,.13,.0005,.02)
    p_t=np.arange(round(.22*sr))/sr
    perc=np.sin(2*np.pi*(310*p_t+8*(1-np.exp(-p_t/.02))))*np.exp(-p_t/.036)*envelope(p_t,.22,.001,.03)

    for index,(track,role) in enumerate(ROLES.items()):
        print(json.dumps({'song':name,'stage':'synthesize','item':index+1,'total':len(ROLES),'instrument':track}),flush=True)
        x=np.zeros((total,2),np.float32)
        for bar in range(config['bars']):
            beat=bar*4; chord=(bar//2)%4; root=roots[chord]; high=voicings[chord]
            strong=active(bar)
            if index==0:
                for k in [v for v in kicks if beat<=v<beat+4]:
                    add(x,kick,k,.95 if k%4==0 else .87); notes[track].append([k,36,.15,115])
            elif index==1 and strong:
                positions=([1,3] if name=='horizon' or not 24<=bar<32 else [2])
                for p in positions:
                    add(x,snare,beat+p+.008,.9);notes[track].append([beat+p+.008,38,.12,108])
                if name=='pulse' and bar%4==3:
                    for p in [2.75,3.25,3.75]:
                        add(x,clap,beat+p,.25 if p<3.75 else .48);notes[track].append([beat+p,38,.08,55])
            elif index==2 and (strong or (name=='horizon' and 40<=bar<44)):
                steps=16 if name=='pulse' and bar>=40 or name=='horizon' and 48<=bar<60 else 8
                for step in range(steps):
                    if step%4==3 and bar%4==0:continue
                    p=step*4/steps+(.032 if step%2 else 0)
                    add(x,hat,beat+p,(.4 if step%2 else .65)*rng.uniform(.8,1.1),(-.28 if step%2 else .28))
                    notes[track].append([beat+p,42,.08,65 if step%2 else 90])
            elif index==3 and strong:
                for p in ([.75,2.75] if name=='horizon' else [.25,1.25,2.75,3.625]):
                    add(x,perc,beat+p,.4+rng.random()*.3,(-.45 if p<2 else .45));notes[track].append([beat+p,62,.15,70])
            elif index==4 and strong:
                pattern=[(.5,.62),(1.75,.36),(2.5,.65),(3.5,.32)] if name=='horizon' else [(0,.46),(.875,.31),(1.5,.42),(2.75,.38),(3.5,.25)]
                if name=='pulse' and 24<=bar<32:pattern=[(0,1.5),(2.75,.7)]
                for p,duration in pattern:hit(x,track,beat+p,root,duration,106,'sub')
            elif index==5 and strong:
                pattern=[(.5,0),(1.25,7),(2.5,0),(3.25,12)] if name=='horizon' else [(p,[0,0,12,7,10,12,0,15][i]) for i,p in enumerate([0,.5,.875,1.5,2,2.75,3.25,3.5])]
                for j,(p,interval) in enumerate(pattern):
                    if name=='pulse' and 24<=bar<32 and j%2:continue
                    hit(x,track,beat+p,root+12+interval,.22 if name=='horizon' else .15,82+(j%3)*9,'bass')
            elif index==6 and bar%2==0:
                for j,pitch in enumerate(high):hit(x,track,beat+j*.025,pitch,7.7,68 if strong else 55,'pad',-.3+j*.15)
            elif index==7 and 4<=bar<config['bars']-3:
                if name=='horizon':
                    motifs=[[(.5,73,.7),(2,76,.5),(3.25,73,.4)],[(0,71,.8),(1.75,69,.55),(3,68,.7)],[(.5,69,1.1),(2.5,73,.6)],[(0,68,.7),(1.5,66,.7),(3,64,.8)]]
                    for p,pitch,duration in motifs[bar%4]:hit(x,track,beat+p,pitch,duration,80+(bar%3)*5,'pluck',.18 if bar%2 else -.18)
                else:
                    positions=[.25,1,1.75,2.625,3.25] if bar%2 else [0,.75,1.5,3]
                    for j,p in enumerate(positions):
                        pitch=[74,77,72,69,65][(j+bar//4)%5]
                        hit(x,track,beat+p,pitch,.13 if bar%4<3 else .28,76+(j%3)*8,'chop',(-.32 if j%2 else .32))
                    if bar>=40 and bar%4==3:hit(x,track,beat+3.5,root+36,.4,98,'bell',0)
            elif index==8 and bar%4==0:
                for pitch in high[1::2]:hit(x,track,beat,pitch+12,15.5,40,'pad')
            elif index==9:
                transitions=[8,16,40,48,60] if name=='horizon' else [8,24,32,40,56,64]
                if bar in [v-2 for v in transitions]:
                    length=round(8*spb*sr);tt=np.arange(length)/sr
                    lift=filt(rng.normal(0,1,(length,2)),[1100,10000],'bandpass')
                    lift*=((tt/tt[-1])**1.7*np.minimum(1,(tt[-1]-tt)/.015))[:,None]
                    add(x,lift,beat,.18)
                if bar in transitions:
                    length=round(2.5*sr);tt=np.arange(length)/sr
                    crash=filt(rng.normal(0,1,(length,2)),[2800,14000],'bandpass')*np.exp(-tt/.75)[:,None]
                    add(x,crash,beat,.11)
        if index in [5,6,7,8]:
            x=filt(x,160 if index>=6 else 120,'highpass')
            if index in [6,8]:
                x=Pedalboard([Chorus(rate_hz=.21,depth=.17,mix=.12),Reverb(room_size=.67 if index==6 else .85,damping=.6,wet_level=.20 if index==6 else .42,dry_level=.8,width=.9)])(x.T,sr).T
            if index==7:
                x=delay(x,.25 if name=='horizon' else .18,.75 if name=='horizon' else .375)
                x=Pedalboard([Reverb(room_size=.48,damping=.65,wet_level=.14,dry_level=.9,width=.8)])(x.T,sr).T
        if index in [4,5,6,7,8]:x*=duck[:,None]**(.65 if index>=6 else 1)
        x[:round(.012*sr)]*=np.linspace(0,1,round(.012*sr))[:,None]
        x[-2*sr:]*=np.linspace(1,0,2*sr)[:,None]
        peak=float(np.max(np.abs(x)))
        if peak<1e-8 or not np.isfinite(x).all():raise ValueError('Invalid stem '+track)
        x*=PEAKS[index]/peak
        file=stems/(track+'.wav');sf.write(file,x,sr,subtype='PCM_24')
        paths.append({'path':ws.relative(file),'role':role,'gain_db':0.0})
    midi=destination/(config['title']+'.mid')
    write_midi(midi,notes,bpm,config['bars']*4)
    plan={'stems':paths,'duck_source':paths[0]['path'],'auto_balance':False,'target_lufs':-12.0,'ceiling_dbtp':-1.0,'max_attempts':2,'tags':['original demo',name,'procedural synthesis']}
    plan_path=destination/'mix-plan.json';plan_path.write_text(json.dumps(plan,indent=2))
    manifest={**config,'duration_seconds':120,'sample_rate':sr,'channels':2,'speaker_playback':False,'artist_audio_used':False,
              'renderer':'Authored procedural synthesis; file DSP, not native Live export','perceptual_listening':False,'creative_acceptance':'pending',
              'midi':midi.name,'note_count':sum(len(v) for v in notes.values()),'sections':[{'bar':b+1,'seconds':b*4*spb,'label':s} for b,s in config['sections']],
              'stems':[{'path':p['path'],'sha256':digest(ws.path(p['path']))} for p in paths]}
    (destination/'composition.json').write_text(json.dumps(manifest,indent=2))
    return {'directory':ws.relative(destination),'plan':ws.relative(plan_path),'composition':manifest}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--song',choices=['horizon','pulse','all'],default='all')
    parser.add_argument('--compose-only',action='store_true',help='Print stems and MIDI; mix later with the CLI or MCP')
    args=parser.parse_args()
    from cli_anything.ableton.production.api import Production
    from cli_anything.ableton.production.workspace import digest
    production=Production(args.workspace)
    for name in (RECIPES if args.song=='all' else [args.song]):
        result=compose(args.workspace,name)
        if not args.compose_only:
            report=production.mix(result['plan'])
            preserved=all(digest(production.workspace.path(s['path']))==s['sha256'] for s in result['composition']['stems'])
            result['render']={**report,'source_files_preserved_verified':preserved}
            if not preserved:raise ValueError('Source hash changed')
        output=production.workspace.path(result['directory'])/'demo-result.json'
        output.write_text(json.dumps(result,indent=2,allow_nan=False))
        print(json.dumps({'song':name,'result':production.workspace.relative(output)}),flush=True)


if __name__=='__main__':
    main()
