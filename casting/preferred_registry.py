"""Build a provisional registry without inventing individual audition approvals."""
import hashlib,json,pathlib,wave
root=pathlib.Path("review")
policy=json.loads(pathlib.Path("casting/preferences.json").read_text())
rows=json.loads((root/"candidates.json").read_text())
assert len(rows)==24 and len({r["id"] for r in rows})==24
voices=[]
for row in rows:
    engine=policy["engine_by_gender"][row["gender"]]
    assert any(e["engine"]==engine and e["eligible"] for e in row["engines"]),row["id"]
    ref=root/row["reference_file"]
    assert hashlib.sha256(ref.read_bytes()).hexdigest()==row["reference_sha256"]
    with wave.open(str(ref)) as w: assert w.getnframes()/w.getframerate()>5.1,row["id"]
    voices.append({"key":row["id"]+"-"+engine,"engine":engine,"category":row["category"],"variant":policy["variant_by_candidate"][row["id"].rsplit("-",1)[1]],"reference_file":row["reference_file"],"reference_sha256":row["reference_sha256"],"reviewed":False,"selection_status":"provisional_user_preference"})
pathlib.Path("preferred-voices.json").write_text(json.dumps({"voices":voices},indent=2))
print("24 provisional voices; 12 Chatterbox male, 12 Pocket female. Individual approval not asserted.")
