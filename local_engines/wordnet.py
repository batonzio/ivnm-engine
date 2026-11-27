"""Princeton WordNet 3.0 adapter; independent sense evidence, never automatic graph merges."""
from pathlib import Path
import re
import unicodedata

VERSION = "3.0"
SOURCE = "Princeton WordNet"
LICENSE = "WordNet"
LICENSE_URL = "https://wordnet.princeton.edu/license-and-commercial-use"
POS = {"n", "v", "a", "s", "r"}

def open_local(directory):
    """Explicit local corpus only. NLTK is optional; never download at runtime."""
    root = Path(directory)
    if not root.is_dir() or not all((root / name).is_file() for name in
        ("data.noun","data.verb","data.adj","data.adv","index.noun","index.verb","index.adj","index.adv")):
        raise ValueError("Local WordNet corpus files required")
    try:
        from nltk.corpus.reader import WordNetCorpusReader
    except ImportError:
        raise RuntimeError("Install the optional NLTK runtime explicitly") from None
    # OMW is not used. Avoid the default global corpus/download configuration.
    reader = WordNetCorpusReader(str(root.resolve()), None)
    if reader.get_version() != VERSION:
        raise ValueError("Unsupported WordNet corpus version")
    return reader

def _term(value):
    if not isinstance(value,str):
        raise ValueError("Invalid lexical query")
    value = " ".join(unicodedata.normalize("NFKC",value).split()).casefold()
    if not value or len(value)>100 or not re.fullmatch(r"[a-z][a-z '\-]*",value):
        raise ValueError("English word or phrase required")
    return value

def _ref(sense):
    pos=sense.pos()
    offset=sense.offset()
    if pos not in POS or type(offset) is not int or not 0<=offset<=99999999:
        raise ValueError("Invalid synset identity")
    return f"pwn:{VERSION}:{pos}:{offset:08d}"

def lookup(reader, term, *, pos=None, limit=20, relation_limit=20):
    """Return bounded sense candidates with source identity and explicit review requirement."""
    term=_term(term)
    if reader.get_version()!=VERSION:
        raise ValueError("Unsupported WordNet corpus version")
    if pos is not None and pos not in POS:
        raise ValueError("Invalid part of speech")
    if type(limit) is not int or not 1<=limit<=50 or type(relation_limit) is not int or not 1<=relation_limit<=50:
        raise ValueError("Invalid result bounds")
    # Keep distinct senses, including adjective satellites. Do not infer CEFR or dialect.
    raw=reader.synsets(term.replace(" ","_"),pos=pos)
    unique={}
    for sense in raw:
        unique.setdefault(_ref(sense),sense)
    result=[]
    for ref,sense in list(unique.items())[:limit]:
        relations={}
        for name in ("hypernyms","hyponyms","similar_tos"):
            ids=sorted({_ref(s) for s in getattr(sense,name)()})
            relations[name]={"ids":ids[:relation_limit],"truncated":len(ids)>relation_limit}
        antonyms={}
        for lemma in sense.lemmas():
            for opposite in lemma.antonyms():
                identity=(lemma.name(),opposite.name(),_ref(opposite.synset()))
                antonyms[identity]={"lemma":identity[0],"antonym":identity[1],"sense_id":identity[2]}
        pairs=sorted(antonyms)
        result.append({"sense_id":ref,"name":sense.name(),"pos":sense.pos(),
                       "definition":sense.definition(),"lemmas":sorted(set(sense.lemma_names())),
                       "relations":relations,"antonyms":[antonyms[k] for k in pairs[:relation_limit]],
                       "antonyms_truncated":len(pairs)>relation_limit,
                       "cefr":None,"british_usage_verified":False,"review_required":True})
    return {"schema_version":1,"query":term,"source":SOURCE,"source_version":VERSION,
            "license":LICENSE,"license_url":LICENSE_URL,"copyright":"WordNet 3.0 Copyright 2006 by Princeton University.",
            "senses":result,"total_senses":len(unique),"truncated":len(unique)>limit,
            "publication_allowed":False}
