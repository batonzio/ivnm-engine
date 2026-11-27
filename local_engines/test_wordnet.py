"""Synthetic lexical fixtures plus explicitly enabled real local corpus smoke."""
import os
import unittest
from .wordnet import lookup, open_local

class Lemma:
    def __init__(self,name,sense): self._name=name; self._sense=sense; self.opposites=[]
    def name(self): return self._name
    def synset(self): return self._sense
    def antonyms(self): return self.opposites

class Sense:
    def __init__(self,offset,pos,name):
        self._offset=offset; self._pos=pos; self._name=name
        self.words=[Lemma(name,self)]; self.parents=[]; self.children=[]
    def offset(self): return self._offset
    def pos(self): return self._pos
    def name(self): return self._name
    def definition(self): return "Synthetic definition"
    def lemmas(self): return self.words
    def lemma_names(self): return [w.name() for w in self.words]
    def hypernyms(self): return self.parents
    def hyponyms(self): return self.children
    def similar_tos(self): return []

class Reader:
    def __init__(self):
        self.a=Sense(1,"n","bank.n.01"); self.b=Sense(2,"n","bank.n.02")
        self.a.parents=[self.b]; self.a.children=[Sense(3,"n","c"),Sense(4,"n","d")]
        self.a.words[0].opposites=[self.b.words[0]]
        self.version="3.0"; self.query=None
    def get_version(self): return self.version
    def synsets(self,term,pos=None):
        self.query=(term,pos)
        return [self.a,self.b,self.a] if term=="bank" else []

class WordNetTests(unittest.TestCase):
    def test_distinct_senses_and_provenance(self):
        reader=Reader()
        r=lookup(reader," BANK ",pos="n")
        self.assertEqual(reader.query,("bank","n"))
        self.assertEqual([s["sense_id"] for s in r["senses"]],["pwn:3.0:n:00000001","pwn:3.0:n:00000002"])
        self.assertTrue(all(s["review_required"] and s["cefr"] is None and not s["british_usage_verified"] for s in r["senses"]))
        self.assertFalse(r["publication_allowed"])
        self.assertEqual(r["license"],"WordNet")

    def test_relations_and_limits(self):
        r=lookup(Reader(),"bank",limit=1,relation_limit=1)
        self.assertTrue(r["truncated"])
        a=r["senses"][0]
        self.assertTrue(a["relations"]["hyponyms"]["truncated"])
        self.assertEqual(a["relations"]["hypernyms"]["ids"],["pwn:3.0:n:00000002"])
        self.assertEqual(a["antonyms"][0]["sense_id"],"pwn:3.0:n:00000002")

    def test_no_match_and_bad_input(self):
        self.assertEqual(lookup(Reader(),"unknown")["senses"],[])
        for term in ("","123","x"*101):
            with self.assertRaises(ValueError): lookup(Reader(),term)
        with self.assertRaises(ValueError): lookup(Reader(),"bank",pos="x")
        with self.assertRaises(ValueError): lookup(Reader(),"bank",limit=0)

    def test_version_and_missing_corpus(self):
        reader=Reader();reader.version="3.1"
        with self.assertRaises(ValueError): lookup(reader,"bank")
        with self.assertRaises(ValueError): open_local("/nonexistent-wordnet-fixture")

    @unittest.skipUnless(os.environ.get("IVNM_WORDNET_DIR"),"Explicit real corpus not provisioned")
    def test_real_local_corpus(self):
        reader=open_local(os.environ["IVNM_WORDNET_DIR"])
        r=lookup(reader,"bank",pos="n")
        self.assertGreater(len(r["senses"]),1)
        self.assertEqual(len({s["sense_id"] for s in r["senses"]}),len(r["senses"]))
