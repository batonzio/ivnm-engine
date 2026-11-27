import unittest
import numpy as np
from continuity import features
class ContinuityTests(unittest.TestCase):
    def test_internal_gap(self):
        sr=24000;rng=np.random.default_rng(4);a=rng.normal(0,.1,sr)
        x=np.r_[np.zeros(sr//10),a,np.zeros(sr//10),a,np.zeros(sr//10)]
        r=features(x,sr)
        self.assertEqual(len(r["bounded_low_energy_gaps"]),1)
        self.assertEqual(r["bounded_low_energy_gaps"][0]["duration_ms"],100)
    def test_duplicate(self):
        sr=24000;a=np.random.default_rng(8).normal(0,.1,1920)
        self.assertTrue(features(np.tile(a,4),sr)["near_duplicate_waveform_windows"])
    def test_sustained_tone(self):
        sr=24000;x=.1*np.sin(2*np.pi*200*np.arange(sr)/sr)
        self.assertFalse(features(x,sr)["near_duplicate_waveform_windows"])
if __name__=="__main__":unittest.main()
