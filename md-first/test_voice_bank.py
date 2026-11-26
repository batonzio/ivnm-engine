import importlib.util, pathlib, unittest
P=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("compiler",P/"compile.py")
compiler=importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)
class MatrixTest(unittest.TestCase):
    def test_coverage(self):
        bank=compiler.BANK
        expected={f"{a}-{b}-{c}" for a in ("UK","CA") for b in ("C","T","A") for c in ("M","F")}
        self.assertEqual(set(bank["slots"]),expected)
        tracks=compiler.compile_md(P/"examples/voice-matrix.md")["tracks"]
        self.assertEqual(len(tracks),12)
        for t in tracks:
            self.assertEqual(t["status"],"blocked")
            self.assertTrue(any("No approved voice for category" in r for r in t["reasons"]))
            self.assertIsNone(t["lines"][0]["voice"])
    def test_existing_demo(self):
        tracks=compiler.compile_md(P/"examples/studio.md")["tracks"]
        self.assertEqual([t["status"] for t in tracks],["blocked","ready"])
if __name__=="__main__": unittest.main()
