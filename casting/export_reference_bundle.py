"""Export only synthetic source references and candidate catalog, never lesson data."""
import hashlib,json,pathlib,re,zipfile
CATALOG_SHA="fc71bb07841b298ab500e4941c4da454b45ece4e0de31181ff4ff52180b413d2"
def sha(data):return hashlib.sha256(data).hexdigest()
root=pathlib.Path("review")
catalog=(root/"candidates.json").read_bytes()
if sha(catalog)!=CATALOG_SHA:raise ValueError("Unexpected catalog")
rows=json.loads(catalog)
assert len(rows)==24 and len({r["id"] for r in rows})==24
with zipfile.ZipFile("ivnm-synthetic-references-v1.zip","w",compression=zipfile.ZIP_DEFLATED) as z:
    def add(name,data):
        entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(entry,data)
    add("candidates.json",catalog)
    for r in sorted(rows,key=lambda x:x["id"]):
        name=r["reference_file"]
        assert re.fullmatch(r"refs/(UK|CA)-(C|T|A)-(M|F)-0[12]-ref\.wav",name)
        data=(root/name).read_bytes()
        assert sha(data)==r["reference_sha256"]
        add(name,data)
print("Reference bundle verified; 24 synthetic source WAV files. No recordings of users, scripts or live lesson data. No individual audition approval.")
