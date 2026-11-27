import unittest
from dataclasses import dataclass
from wheat_pair_exact_qualification import canonical

@dataclass(frozen=True)
class Key:
    source: str
    contig: str

@dataclass
class Admission:
    rows: dict
    masks: dict
    policy: tuple

class QualificationTests(unittest.TestCase):
    def test_nested_dataclass_keys_and_every_field_are_retained(self):
        value=Admission({"a":[1,True,None,1.2]}, {Key("a","x"):((100,200),)}, ("threshold",100))
        got=canonical(value)
        self.assertEqual([x[0] for x in got["fields"]],["rows","masks","policy"])
        masks=got["fields"][1][1]["$mapping"]
        self.assertEqual(masks[0][0], {"$type":"Key","fields":[["source","a"],["contig","x"]]})
        self.assertNotEqual(got,canonical(Admission(value.rows,value.masks,("threshold",101))))
        self.assertNotEqual(canonical((1,)),canonical([1]))
    def test_sets_canonicalize_but_sequence_order_is_preserved(self):
        self.assertEqual(canonical(set([3,1,2])),canonical(set([1,2,3])))
        self.assertNotEqual(canonical([1,2]),canonical([2,1]))

    def test_reference_workers_cannot_satisfy_pair_worker_gate(self):
        import gzip, json, tempfile
        from pathlib import Path
        from hashlib import sha256
        from wheat_pair_exact_qualification import compare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=b'{"complete":"same fields"}'
            for label in ("baseline","candidate"):
                with gzip.open(root/(label+"-admission.json.gz"),"wb") as f:f.write(payload)
                (root/(label+"-tools.tgz")).write_bytes(b"bound archive")
                report={"output_sha256":sha256(payload).hexdigest(),"input_sha256":"same-input","elapsed_s":1,
                        "selector_identity":"q0-selector-4eec44d14ec5dd92e2543f64",
                        "logs":["reference screen complete: parts=65 worker_parts=12",
                                "placement pair work round=1: owner_parts=54 worker_parts=0 new_relations=170"]}
                (root/(label+".json")).write_text(json.dumps(report))
            (root/"subset.json").write_text(json.dumps({"input_sha256":"same-input"}))
            with self.assertRaisesRegex(ValueError,"did not exercise workers"):
                compare(root)
            self.assertFalse(json.loads((root/"qualification.json").read_text())["real_worker_dispatch_verified"])
