from pathlib import Path
import unittest

from probe_regional_dp_cap_ladder import argv_for


class CapLadderTests(unittest.TestCase):
    def case(self):
        return {'argv':['mm2','-c','-x','asm10','-D','-P','--dual=yes','--no-long-join','-m','2000','-t','2','oldT','oldQ'],
                'paths':{'target.fa':Path('/tmp/T'),'query.fa':Path('/tmp/Q')}}

    def test_cap_is_only_mapped_option_change(self):
        c=self.case()
        base=argv_for(c,'original')
        self.assertEqual(base,[*c['argv'][:-2],'/tmp/T','/tmp/Q'])
        self.assertEqual(argv_for(c,'30m'),[*base[:-2],'--cap-sw-mem','30m',*base[-2:]])
        self.assertEqual(argv_for(c,'10m'),[*base[:-2],'--cap-sw-mem','10m',*base[-2:]])

    def test_rejects_unknown_profile_or_more_threads(self):
        with self.assertRaises(ValueError):
            argv_for(self.case(),'1m')
        c=self.case(); c['argv'][-3]='4'
        with self.assertRaises(ValueError):
            argv_for(c,'30m')

    def test_never_overrides_an_archived_explicit_cap(self):
        c=self.case(); c['argv'][2:2]=['--cap-sw-mem','50m']
        with self.assertRaises(ValueError):
            argv_for(c,'10m')
