import hashlib
import io
import tempfile
import unittest
from pathlib import Path

import check_wheat_derived_inputs as p


class DerivedParentTests(unittest.TestCase):
    def trial(self):
        # Source order differs from bytewise alias order; keep lower case and wrapped CRLF lines.
        raw = b'>z\r\nAc\r\nGT\r\n>a\nTT\n'
        records = [(b'z', (4, 4, 2, 4)), (b'a', (2, 15, 2, 3))]
        batches = [{'entries': [{'name': 'gpm_pair_000000002b', 'length': 4}]},
                   {'entries': [{'name': 'gpm_pair_000000001b', 'length': 2}]}]
        first, second = b'>gpm_pair_000000002b\nAcGT\n', b'>gpm_pair_000000001b\nTT\n'
        payloads = {p.PART: b'>z\nAcGT\n>a\nTT\n', p.BASE+'/self_name_map.tsv':
                    b'gpm_pair_000000002a\tz\ngpm_pair_000000002b\tz\ngpm_pair_000000001a\ta\ngpm_pair_000000001b\ta\n',
                    p.BASE+'/self_target.fa': b'>gpm_pair_000000002a\nAcGT\n>gpm_pair_000000001a\nTT\n',
                    p.BASE+'/self_query.fa': first+second, p.BASE+'/batches/batch-00000/query.fa': first,
                    p.BASE+'/batches/batch-00001/query.fa': second}
        return raw, records, batches, {k: {'size': len(v), 'sha256': hashlib.sha256(v).hexdigest()} for k,v in payloads.items()}

    def test_original_roles_are_byte_exact(self):
        raw, records, batches, expected = self.trial()
        self.assertEqual(p.replay(io.BytesIO(raw), records, batches, expected), 8)

    def test_changed_source_alias_or_parent_digest_rejected(self):
        for case in ('source', 'mode', 'sha', 'order'):
            with self.subTest(case=case):
                raw, records, batches, expected = self.trial()
                if case == 'source': raw = raw.replace(b'Ac', b'AC')
                if case == 'mode': batches[0]['entries'][0]['name'] = 'gpm_pair_000000002a'
                if case == 'sha': expected[p.BASE+'/self_query.fa']['sha256'] = '0'*64
                if case == 'order': records.reverse()
                with self.assertRaises(ValueError): p.replay(io.BytesIO(raw), records, batches, expected)

    def test_no_linked_or_escaping_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'a').write_bytes(b'a'); (root/'l').symlink_to(root/'a')
            for n in ('l', '../a', '/a'):
                with self.assertRaises(ValueError): p.member(root,n)


if __name__ == '__main__': unittest.main()
