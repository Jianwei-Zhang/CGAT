from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[2])]
import source_part_lookup as lookup
from server.tools.lgz_core.common import stable_id


class SourceLookupTests(unittest.TestCase):
    def inputs(self):
        sources=[('a','same',100),('b','same',100),('a','other',100)]
        members={stable_id('q0-source-part',[d,n,0,length,sha]):sha
                 for (d,n,length),sha in zip(sources,['a'*64,'a'*64,'b'*64])}
        return members,{key:100 for key in members},sources

    def test_equal_lengths_and_shared_names_still_require_exact_identity(self):
        members,hints,sources=self.inputs();mapped,trials=lookup.invert(members,hints,sources,stable_id)
        self.assertEqual({(r['dataset'],r['contig']) for r in mapped.values()},{(d,n) for d,n,_ in sources})
        self.assertEqual(trials,9)

    def test_split_or_wrong_digest_is_not_guessed_from_length(self):
        members,hints,sources=self.inputs();key=next(iter(members));members[key]='c'*64
        with self.assertRaises(ValueError):lookup.invert(members,hints,sources,stable_id)
        key=stable_id('q0-source-part',['a','same',10,110,'a'*64])
        with self.assertRaises(ValueError):lookup.invert({key:'a'*64},{key:100},[('a','same',100)],stable_id)

    def test_budget_and_incomplete_inventory_fail(self):
        members,hints,sources=self.inputs()
        with self.assertRaises(ValueError):lookup.invert(members,hints,sources,stable_id,maximum_trials=8)
        with self.assertRaises(ValueError):lookup.invert(members,{},sources,stable_id)


if __name__=='__main__':unittest.main()
