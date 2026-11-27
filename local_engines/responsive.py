"""Mobile geometry evidence for existing Playwright/axe G4/G5 runners."""
import re

VIEWS=((360,800),(390,844),(430,932))
TEXT_FLOOR=16
TOLERANCE=3
STATE=re.compile(r"[A-Za-z0-9_.:-]{1,100}")

# No text, answers, URLs, screenshots or selectors in the report.
# Measurements are taken from an existing trusted local page/state.
PROBE="""() => {
 const root=document.documentElement, body=document.body;
 const vw=root.clientWidth;
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return e.getClientRects().length>0 && r.width>0 && r.height>0 &&
 s.visibility!=='hidden' && s.display!=='none' &&
 !e.closest('[hidden],[aria-hidden="true"]');};
 const elems=[...document.querySelectorAll('.slide')].filter(visible);
 const scope=elems.length===1?elems[0]:body;
 const all=[scope,...scope.querySelectorAll('*')].filter(visible);
 let outside=0, clipped=0, horizontal=0;
 for(const e of all){
   const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   if(r.left < -3 || r.right>vw+3)outside++;
   if(e.clientWidth>0 && e.scrollWidth>e.clientWidth+3 &&
      ['hidden','clip','auto','scroll'].includes(s.overflowX))horizontal++;
   if(e.clientHeight>0 && e.scrollHeight>e.clientHeight+3 &&
      ['hidden','clip'].includes(s.overflowY))clipped++;
 }
 const sizes=[...scope.querySelectorAll('p,li,.instruction,.question>span:first-child,input,select,textarea,button')]
   .filter(e=>visible(e)&&(e.textContent.trim()||['INPUT','SELECT','TEXTAREA'].includes(e.tagName)))
   .map(e=>parseFloat(getComputedStyle(e).fontSize));
 const targets=[...scope.querySelectorAll('button,a[href],input,select,textarea,[role="button"]')]
   .filter(visible).map(e=>{const r=e.getBoundingClientRect();return Math.min(r.width,r.height);});
 const meta=document.querySelector('meta[name="viewport"]');
 return {layout_width:vw,document_width:Math.max(root.scrollWidth,body.scrollWidth),
   visible_slides:elems.length,viewport_meta:!!meta && /width\\s*=\\s*device-width/i.test(meta.content),
   outside_count:outside,horizontal_count:horizontal,clipped_count:clipped,
   tiny_text_count:sizes.filter(x=>x<16).length,small_targets:targets.filter(x=>x<24).length};
}"""

def _int(value,lo=0,hi=1000000):
    if type(value) is not int or not lo<=value<=hi:
        raise ValueError("Invalid geometry metric")
    return value

def probe(page):
    """Use caller's already configured Playwright page. No new browser or network."""
    return page.evaluate(PROBE)

def checks(metrics,width,height,state,*,require_slide=True):
    if (width,height) not in VIEWS or not isinstance(state,str) or not STATE.fullmatch(state):
        raise ValueError("Unexpected viewport or state ID")
    for field in ("layout_width","document_width","visible_slides","outside_count",
                  "horizontal_count","clipped_count","tiny_text_count","small_targets"):
        _int(metrics[field])
    if type(metrics["viewport_meta"]) is not bool:
        raise ValueError("Invalid viewport meta metric")
    if type(require_slide) is not bool: raise ValueError("Invalid slide policy")
    result=[]
    def add(gate,code,ok,value,review=False):
        result.append({"gate":gate,"code":code,"status":"PASS" if ok else "REVIEW" if review else "FAIL",
                       "detail":{"where":f"{width}x{height}/{state}","count":value}})
    add("G4","MOBILE_VIEWPORT",metrics["viewport_meta"] and abs(metrics["layout_width"]-width)<=TOLERANCE,metrics["layout_width"])
    add("G4","MOBILE_HORIZONTAL_OVERFLOW",metrics["document_width"]<=width+TOLERANCE and metrics["outside_count"]==0 and metrics["horizontal_count"]==0,metrics["outside_count"]+metrics["horizontal_count"])
    add("G4","MOBILE_CLIPPED_CONTENT",metrics["clipped_count"]==0,metrics["clipped_count"])
    add("G4","MOBILE_TEXT_FLOOR",metrics["tiny_text_count"]==0,metrics["tiny_text_count"],review=True)
    add("G5","MOBILE_TARGET_FLOOR",metrics["small_targets"]==0,metrics["small_targets"],review=True)
    if require_slide:
        add("G5","MOBILE_ONE_VISIBLE_SLIDE",metrics["visible_slides"]==1,metrics["visible_slides"])
    return result

def aggregate(samples,*,expected_states,require_slide=True):
    """Coverage is mandatory; all expected states at every mobile viewport."""
    if not isinstance(expected_states,(list,tuple)) or not expected_states or len(expected_states)>300:
        raise ValueError("Explicit expected states required")
    if any(not isinstance(s,str) or not STATE.fullmatch(s) for s in expected_states) or len(set(expected_states))!=len(expected_states):
        raise ValueError("Invalid state list")
    expected={(w,h,s) for w,h in VIEWS for s in expected_states}
    seen=set(); report={"G4":[],"G5":[]}
    for sample in samples:
        key=(sample["width"],sample["height"],sample["state"])
        if key not in expected or key in seen: raise ValueError("Unexpected or duplicate sample")
        seen.add(key)
        for row in checks(sample["metrics"],*key,require_slide=require_slide):
            report[row["gate"]].append({k:v for k,v in row.items() if k!="gate"})
    missing=sorted(expected-seen)
    report["G5"].append({"code":"MOBILE_COVERAGE","status":"FAIL" if missing else "PASS",
                         "detail":{"missing":[f"{w}x{h}/{s}" for w,h,s in missing]}})
    statuses={r["status"] for rows in report.values() for r in rows}
    return {"schema_version":1,"status":"BLOCKED" if "FAIL" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS",
            "gates":report,"publish_authorized":False}
