import unittest
from probe_fork_native_cache import transfer_budget


class TransferTest(unittest.TestCase):
    def test_same_bytes_not_same_size_decides_transfer_bound(self):
        rows=[{'sha256':key*64,'size':n} for key,n in [('0',9),('1',9),('0',9),('2',3)]]
        self.assertEqual(transfer_budget(rows),{'logical_output_bytes':30,'unique_payload_bytes':21,'repeated_bytes':9})
        with self.assertRaises(ValueError):transfer_budget(rows+[{'sha256':'0'*64,'size':10}])
