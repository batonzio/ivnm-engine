import pathlib,tempfile,unittest,sys
import numpy as np
import soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"audio-qa"))
from mastering import trim_edges,noise_floor,repetition_report,cleanup,master,measure
class PostTests(unittest.TestCase):
    def test_trim_keeps_interior(self):
        sr=24000;speech=.1*np.sin(np.arange(sr)*.1)
        x=np.r_[np.zeros(sr),speech,np.zeros(sr//2),speech,np.zeros(sr)].astype("float32")
        y,r=trim_edges(x,sr)
        self.assertEqual(r["leading_ms"],350);self.assertEqual(r["trailing_ms"],350)
        np.testing.assert_array_equal(y,x[8400:-8400])
    def test_repeat(self):
        self.assertTrue(repetition_report("I went home","I I went home",[])["unexpected_repetitions"])
        self.assertFalse(repetition_report("very very good","very very good",[])["unexpected_repetitions"])
        self.assertTrue(repetition_report("go to school","go to go to school",[])["unexpected_repetitions"])
    def test_cleanup_and_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp);sr=24000;t=np.arange(sr*4)/sr
            x=(.07*np.sin(2*np.pi*220*t)+.02*np.sin(2*np.pi*740*t))*(.65+.35*np.sin(2*np.pi*2*t))
            raw=p/"raw.wav";clean=p/"clean.wav";sf.write(raw,x,sr,subtype="PCM_24")
            original=raw.read_bytes();r=cleanup(raw,clean)
            self.assertEqual(raw.read_bytes(),original)
            self.assertEqual(r["speed"],1)
            r=master(clean,p/"master.wav",p/"master.mp3")
            self.assertTrue(r["passed"]);self.assertAlmostEqual(measure(p/"master.mp3")["input_i"],-18,delta=1.5)
if __name__=="__main__":unittest.main()
