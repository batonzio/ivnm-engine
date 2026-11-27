import copy,pathlib,sys,unittest,importlib.util
import yaml
from director import normalize,classify,apply
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("compiler",ROOT/"md-first/compile.py")
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
class DirectorTests(unittest.TestCase):
    def test_clock(self):
        text,changes,warnings=normalize("Meet me at 7:30.")
        self.assertEqual(text,"Meet me at seven thirty.")
        self.assertEqual(len(changes),1)
        self.assertEqual(normalize("Code 7:30, date 12/11, 3.14, at 7:05.")[0],"Code 7:30, date 12/11, 3.14, at 7:05.")
        self.assertEqual(normalize("Meet at 7:30.",["7:30"])[0],"Meet at 7:30.")
    def test_intents(self):
        self.assertEqual(classify("Could you help me?"),"request")
        self.assertEqual(classify("Really? What happened?"),"reaction")
        self.assertEqual(classify("Where are you going?"),"question")
    def plan(self):
        src=ROOT/"speech-director/probe.md"
        return compiler.compile_md(src),[yaml.safe_load(b) for b in compiler.BLOCK.findall(src.read_text())]
    def test_plan(self):
        plan,blocks=self.plan();before=copy.deepcopy(plan)
        apply(plan,blocks,compiler.PRESETS["capabilities"])
        t=plan["tracks"][0];a,b,c=t["lines"]
        self.assertEqual(a["pause_after_ms"],420)
        self.assertEqual(b["pause_after_ms"],275)
        self.assertEqual(b["emotion"],"neutral")
        self.assertEqual(b["director"]["emotion_hint"],"joyful")
        self.assertEqual(c["emotion"],"surprised")
        self.assertEqual(a["synthesis_text"],"Can you meet me at seven thirty?")
        for x,y in zip(t["lines"],before["tracks"][0]["lines"]):
            self.assertEqual((x["text"],x["voice_key"],x["speaker"]),(y["text"],y["voice_key"],y["speaker"]))
        self.assertEqual(t["status"],before["tracks"][0]["status"])
    def test_legacy(self):
        src=ROOT/"md-first/examples/router.md"
        plan=compiler.compile_md(src);before=copy.deepcopy(plan)
        apply(plan,[yaml.safe_load(b) for b in compiler.BLOCK.findall(src.read_text())],compiler.PRESETS["capabilities"])
        self.assertEqual(plan,before)
    def test_no_gate_relaxation(self):
        src=ROOT/"md-first/examples/voice-matrix.md"
        plan=compiler.compile_md(src);blocks=[yaml.safe_load(b) for b in compiler.BLOCK.findall(src.read_text())]
        for b in blocks:b["director"]="lite"
        apply(plan,blocks,compiler.PRESETS["capabilities"])
        self.assertTrue(all(t["status"]=="blocked" for t in plan["tracks"]))
if __name__=="__main__":unittest.main()
