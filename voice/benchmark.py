import os, json, re, time, pathlib, subprocess, random
import numpy as np
import soundfile as sf
out = pathlib.Path("out")
out.mkdir(exist_ok=True)
engine = os.environ["ENGINE"]
random.seed(42)
np.random.seed(42)
start = time.monotonic()
if engine == "pocket":
    from pocket_tts import TTSModel
    model = TTSModel.load_model()
    voices = {"A": "alba", "B": "marius"}
    states = {v: model.get_state_for_audio_prompt(v) for v in voices.values()}
    def synth(text, role, path):
        audio = model.generate_audio(states[voices[role]], text)
        sf.write(path, audio.detach().cpu().numpy(), model.sample_rate)
elif engine == "kitten":
    from kitten_tts_cpp import KittenTTS
    model = KittenTTS("KittenML/kitten-tts-2", decoder="student_w4", threads=2)
    voices = {"A": "Bella", "B": "Bruno"}
    def synth(text, role, path):
        model.generate_to_file(text, str(path), voice=voices[role])
else:
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    import torchaudio
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    voices = {"A": "default"}
    def synth(text, role, path):
        torchaudio.save(str(path), model.generate(text).detach().cpu(), model.sr)
load_seconds = time.monotonic()-start
scripts = {
    "vocabulary": [("A","Cupboard. Comfortable. Thought. Through. Clothes. Furniture. Temperature. Adventure.")],
    "school_monologue": [("A","Last Saturday, I was walking home from the library when I noticed a small dog near the bus stop."),("A","It was raining heavily, and the dog looked frightened. I called my neighbour, who helped me find its owner."),("A","By the time we got home, it was nearly six o'clock. I was tired, but I felt relieved.")],
    "dialogue": [("A","Hi, are you still coming to the exhibition tomorrow?"),("B","Yes, of course. What time does it start?"),("A","At half past ten, but we could meet outside the station at ten."),("B","That sounds great. Shall we have lunch afterwards?"),("A","Good idea. There's a little cafe opposite the museum."),("B","Perfect. See you tomorrow!")],
    "celpip_notice": [("A","Good morning. This is a reminder that the community centre will close early on Friday because of maintenance."),("A","The evening swimming lesson has been moved to Saturday at quarter past nine. If you cannot attend, please contact the reception desk before Thursday."),("A","You can choose a different class or request a refund. Thank you for your patience.")]
}
report = {"engine":engine,"quality_gate":"signal only; human audition required","voices":voices,"speed":"native 1x; no time stretching","accent":"unverified","load_seconds":round(load_seconds,2),"tracks":{}}
def ff(*args):
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",*map(str,args)],check=True)
for name, lines in scripts.items():
    if any(role not in voices for role,_ in lines):
        report["tracks"][name] = {"status":"skipped: second reference voice not configured"}
        continue
    t = time.monotonic()
    pieces = []
    for i,(role,text) in enumerate(lines):
        raw = out / f"{name}-{i:02d}-{role}.wav"
        synth(text,role,raw)
        normalized = raw.with_suffix(".pcm.wav")
        ff("-i",raw,"-ac","1","-ar","24000","-c:a","pcm_s16le",normalized)
        data,sr = sf.read(normalized,dtype="float32")
        assert len(data) > sr*0.25 and np.isfinite(data).all() and np.max(np.abs(data)) > .001, f"Invalid audio: {raw}"
        pieces.append(data)
        normalized.unlink()
        if i+1 < len(lines):
            pieces.append(np.zeros(int(sr*.45),dtype=np.float32))
    full = np.concatenate(pieces)
    wave = out / f"{name}.wav"
    sf.write(wave,full,24000)
    mp3 = out / f"{name}.mp3"
    ff("-i",wave,"-af","loudnorm=I=-18:TP=-2:LRA=7","-ar","24000","-ac","1","-c:a","libmp3lame","-b:a","96k",mp3)
    word_count = sum(len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",txt)) for _,txt in lines)
    seconds = len(full)/24000
    report["tracks"][name] = {"status":"generated; listening review required","duration_seconds":round(seconds,2),"words":word_count,"words_per_minute":round(word_count*60/seconds,1),"generation_seconds":round(time.monotonic()-t,2),"script":[{"role":role,"text":txt} for role,txt in lines]}
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print(name,report["tracks"][name],flush=True)
(out/"report.json").write_text(json.dumps(report,indent=2))
