import unittest
import numpy as np
from quality import tokens,edits,signal,evaluate,select
class QualityTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(edits("I'm here. We don't know.","I am here, we do not know")["errors"],0)
    def test_missing_and_added(self):
        self.assertEqual(edits("one two three","one three")["deletions"],1)
        self.assertEqual(edits("one two","one two three")["insertions"],1)
        self.assertEqual(edits("one two","one four")["substitutions"],1)
    def test_truncated(self):
        self.assertFalse(signal(np.full(4000,.2),24000,"We are going to the library tomorrow morning")["passed"])
    def test_silence_and_nan(self):
        self.assertFalse(signal(np.zeros(24000),24000,"Hello")["passed"])
        self.assertFalse(signal(np.array([np.nan]),24000,"Hello")["passed"])
    def test_select(self):
        x=.1*np.sin(np.arange(48000)*.1)
        a={"seed":1,"qa":evaluate(x,24000,"I am here","I am here")}
        b={"seed":2,"qa":evaluate(x,24000,"I am here","I am")}
        self.assertIs(select([b,a]),a)
        self.assertIsNone(select([b]))
if __name__=="__main__": unittest.main()
