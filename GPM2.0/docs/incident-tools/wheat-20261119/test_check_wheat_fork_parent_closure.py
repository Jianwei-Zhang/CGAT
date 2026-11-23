import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from check_wheat_fork_parent_closure import add,same_rows,sealed,sizes
from hashlib import sha256


class ClosureTests(unittest.TestCase):
    def test_union_reuses_content_not_filenames_and_rejects_conflicts(self):
        digest=sha256(b'ab').hexdigest(); a={'path':'a','size':2,'sha256':digest}; b={**a,'path':'b'}
        by_path={};add([a,b,a],by_path)
        self.assertEqual(sizes(by_path),{'paths':2,'logical_bytes':4,'unique_payload_bytes':2})
        with self.assertRaises(ValueError):add([{**a,'sha256':sha256(b'zz').hexdigest()}],by_path)
        with self.assertRaises(ValueError):sizes({'a':a,'b':{**b,'size':3}})
        self.assertTrue(same_rows([b,a],[a,b]));self.assertFalse(same_rows([a,b],[a]));self.assertFalse(same_rows([a,b,a],[a,b]))

    def test_parent_pin_and_relative_members_cannot_be_substituted(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'receipt';raw=b'{"status":"success"}';p.write_bytes(raw);h=sha256(raw).hexdigest();self.assertEqual(sealed(p,h),raw)
            p.write_bytes(b'{"status":"success", "changed":true}')
            with self.assertRaises(ValueError):sealed(p,h)
            for x in ('../outside','/abs','../',''):
                with self.assertRaises(ValueError):add([{'path':x,'sha256':h,'size':1}],{})
