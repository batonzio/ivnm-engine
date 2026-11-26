import hashlib,json,pathlib
p=pathlib.Path("refs");voices=[]
for key,engine,name in [("lab_chatterbox","chatterbox","CA-A-M-01-ref.wav"),("lab_pocket","pocket","CA-A-M-02-ref.wav")]:
    f=p/name;voices.append({"key":key,"engine":engine,"category":"CA-A-M","reference_file":name,"reference_sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"reviewed":False})
pathlib.Path("demo-registry.json").write_text(json.dumps({"voices":voices},indent=2))
