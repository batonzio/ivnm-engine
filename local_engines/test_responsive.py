"""Pure geometry contract and optional real Chromium fixture."""
import os
import unittest
from .responsive import VIEWS, aggregate, probe

def sample(w,h,state="s1",**overrides):
    return {"width":w,"height":h,"state":state,"metrics":{
        "layout_width":w,"document_width":w,"visible_slides":1,"viewport_meta":True,
        "outside_count":0,"horizontal_count":0,"clipped_count":0,
        "tiny_text_count":0,"small_targets":0,**overrides}}

class ResponsiveTests(unittest.TestCase):
    def test_coverage_and_vertical_scroll_allowed(self):
        data=[sample(w,h) for w,h in VIEWS]
        r=aggregate(data,expected_states=["s1"])
        self.assertEqual(r["status"],"PASS")
        self.assertFalse(r["publish_authorized"])
        self.assertEqual(aggregate(data[:-1],expected_states=["s1"])["status"],"BLOCKED")

    def test_horizontal_clip_and_wrong_viewport_block(self):
        for bad in ({"document_width":500},{"horizontal_count":1},{"outside_count":1},
                    {"clipped_count":1},{"viewport_meta":False},{"layout_width":980},{"visible_slides":2}):
            rows=[sample(w,h,**bad) for w,h in VIEWS]
            self.assertEqual(aggregate(rows,expected_states=["s1"])["status"],"BLOCKED")

    def test_tiny_and_small_targets_review(self):
        r=aggregate([sample(w,h,tiny_text_count=1,small_targets=2) for w,h in VIEWS],expected_states=["s1"])
        self.assertEqual(r["status"],"REVIEW")

    def test_bad_and_duplicate_samples(self):
        rows=[sample(w,h) for w,h in VIEWS]
        with self.assertRaises(ValueError): aggregate(rows+[rows[0]],expected_states=["s1"])
        with self.assertRaises(ValueError): aggregate([sample(*VIEWS[0],document_width=-1)],expected_states=["s1"])

    def test_portal_without_slides(self):
        rows=[sample(w,h,visible_slides=0) for w,h in VIEWS]
        self.assertEqual(aggregate(rows,expected_states=["s1"],require_slide=False)["status"],"PASS")

@unittest.skipUnless(os.environ.get("IVNM_BROWSER_SMOKE")=="1","Explicit browser smoke environment required")
class RealBrowserTests(unittest.TestCase):
    def test_good_and_bad_layout(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            try:
                good=[];bad=[]
                for w,h in VIEWS:
                    page=browser.new_page(viewport={"width":w,"height":h},is_mobile=True,has_touch=True)
                    page.route("**/*",lambda route:route.abort())
                    page.set_content('<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;font:16px sans-serif}button{font:inherit;min-height:44px}</style><article class="slide"><p>Fixture</p><button>Next</button><div style="height:1800px">Vertical scroll is permitted.</div></article>')
                    good.append({"width":w,"height":h,"state":"s1","metrics":probe(page)})
                    page.locator(".slide").evaluate("e=>e.style.width='1200px'")
                    bad.append({"width":w,"height":h,"state":"s1","metrics":probe(page)})
                    page.close()
                self.assertEqual(aggregate(good,expected_states=["s1"])["status"],"PASS")
                self.assertEqual(aggregate(bad,expected_states=["s1"])["status"],"BLOCKED")
            finally: browser.close()
