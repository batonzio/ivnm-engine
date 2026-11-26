import unittest
import numpy as np
from quality import tokens,edits,signal,evaluate,select
class QualityTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(edits("I'm here. We don't know.","I am here, we do not know")["errors"],0)
    def test_numeric_spelling(self):
        self.assertEqual(edits("half past ten","half past 10")["errors"],0)
        self.assertEqual(edits("twenty-five minutes","25 minutes")["errors"],0)
        self.assertNotEqual(edits("half past ten","half past 11")["errors"],0)
        self.assertNotEqual(edits("seven","07")["errors"],0)
    def test_british_spelling(self):
        self.assertEqual(edits("I'm usually organised","I'm usually organized")["errors"],0)
        self.assertEqual(edits("My favourite colour is grey","My favorite color is gray")["errors"],0)
        self.assertEqual(edits("We travelled to the town centre","We traveled to the town center")["errors"],0)
        self.assertNotEqual(edits("I am organised","I am organising")["errors"],0)
        self.assertNotEqual(edits("I went to the centre","I went to the cinema")["errors"],0)
        self.assertNotEqual(edits("I am quite creative","I am quiet creative")["errors"],0)
        self.assertNotEqual(edits("I feel well","I feel while")["errors"],0)
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
