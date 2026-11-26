"""Build an offline audition page from existing artifacts; no synthesis."""
import hashlib,html,json,pathlib,re,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
bank=json.loads((ROOT/"voice/voice-bank.json").read_text())
base=pathlib.Path("review-input");out=pathlib.Path("review");out.mkdir(exist_ok=True)
(out/"refs").mkdir(exist_ok=True);(out/"audio").mkdir(exist_ok=True)
def find(root,name):
    found=list(root.rglob(name))
    return found[0] if len(found)==1 else None
def copy(p,target):
    shutil.copyfile(p,target)
    return target.relative_to(out).as_posix()
rows=[]
for category,slot in bank["slots"].items():
    for n in (1,2):
        name=f"{category}-{n:02d}"
        refroot=base/"repaired" if category=="CA-A-M" else base/"chatterbox"
        ref=find(refroot,name+"-ref.wav")
        if not ref:raise RuntimeError("Missing reference "+name)
        path=copy(ref,out/"refs"/ref.name)
        row={"id":name,"category":category,"accent":slot["accent"],"age":slot["perceived_age"],"gender":slot["gender"],"reference_file":path,"reference_sha256":hashlib.sha256(ref.read_bytes()).hexdigest(),"engines":[]}
        for engine in ("chatterbox","pocket","kitten"):
            source=refroot if engine=="chatterbox" else base/engine
            if engine=="kitten":
                # Use repaired artifacts first. Do not show stale CA-A-M-01 generated from replaced reference.
                preferred=base/"kitten-repaired"
                p=find(preferred,name+"-audition.mp3")
                if not p and name!="CA-A-M-01":p=find(source,name+"-audition.mp3")
            else:p=find(source,name+"-audition.mp3")
            if p:
                audio=copy(p,out/"audio"/f"{name}-{engine}.mp3")
                row["engines"].append({"engine":engine,"audio":audio,"eligible":engine!="kitten"})
        rows.append(row)
(out/"candidates.json").write_text(json.dumps(rows,indent=2))
cards=[]
for r in rows:
    items="".join(f'<div><b>{html.escape(e["engine"])}</b> {"— сравнение, C++ профиль пока не готов" if not e["eligible"] else ""}<audio controls preload="none" src="{e["audio"]}"></audio></div>' for e in r["engines"])
    options="".join(f'<option value="{e["engine"]}">{e["engine"]}</option>' for e in r["engines"] if e["eligible"])
    cards.append(f'<section data-id="{r["id"]}"><h2>{r["id"]} · {r["accent"]}, {r["age"]}, {r["gender"]}</h2><details><summary>Исходный референс</summary><audio controls preload="none" src="{r["reference_file"]}"></audio></details>{items}<label>Модель <select class="engine"><option value="">Не выбран</option>{options}</select></label><label>Позиция <select class="variant"><option value="primary">Основной</option><option value="alternate">Запасной</option></select></label><div class="checks">{"".join(f'<label><input type="checkbox" class="{key}">{label}</label>' for key,label in [("accent_ok","Акцент"),("age_ok","Возраст"),("gender_ok","Голос соответствует категории"),("naturalness_ok","Естественность")])}</div></section>')
page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>IVNM Voice Bank</title><style>body{background:#f5f5f4;color:#202124;font:16px system-ui;margin:0 auto;max-width:1050px;padding:24px}section{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin:12px 0}h2{font-size:19px}audio{display:block;width:100%;margin:6px 0 14px}label{display:inline-block;margin:6px 14px 6px 0}button,select{font:inherit;padding:9px}header{position:sticky;top:0;background:#f5f5f4;padding:8px 0;z-index:1}.checks{display:flex;flex-wrap:wrap}#status{white-space:pre-wrap}</style><header><h1>IVNM · прослушивание 24 дикторов</h1><p>Оцени акцент, возраст, тембр и естественность. Для каждой категории выбирай до двух разных дикторов. Kitten оставлен для сравнения: подготовка его C++ профилей ещё не завершена.</p><button id="save">Экспорт выбранных голосов</button> <span id="status"></span></header>'''+''.join(cards)+'''<script>
const rows=DATA;
document.querySelector('#save').onclick=()=>{
 const voices=[],used=new Set();let skipped=0;
 for(const row of rows){
  const section=document.querySelector('[data-id="'+row.id+'"]'),engine=section.querySelector('.engine').value;
  if(!engine){skipped++;continue}
  const checks=Object.fromEntries(['accent_ok','age_ok','gender_ok','naturalness_ok'].map(k=>[k,section.querySelector('.'+k).checked]));
  if(!Object.values(checks).every(Boolean)){alert('Подтверди четыре критерия для '+row.id);return}
  const variant=section.querySelector('.variant').value,key=row.category+'-'+variant;
  if(used.has(key)){alert('Дублируется позиция '+key);return}used.add(key);
  voices.push({key:row.id+'-'+engine,engine,category:row.category,variant,reference_file:row.reference_file,reference_sha256:row.reference_sha256,reviewed:true,...checks})
 }
 if(!voices.length){alert('Ничего не выбрано');return}
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({voices},null,2)],{type:'application/json'}));a.download='approved-voices.json';a.click();URL.revokeObjectURL(a.href);
 document.querySelector('#status').textContent='Экспортировано '+voices.length+'/24. Не выбрано: '+skipped+'.';
}
</script></html>'''
(out/"index.html").write_text(page.replace("const rows=DATA;","const rows="+json.dumps(rows,ensure_ascii=False).replace("</","<\\/")+";"),encoding="utf-8")
print("Candidates",len(rows),"available comparisons",sum(len(r["engines"]) for r in rows))
