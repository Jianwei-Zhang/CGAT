"""Both command scripts must retain the same exact N-run coordinate contract."""
import ast
import itertools
import random
import unittest
from pathlib import Path

TOOLS = Path(__file__).parents[1] / "tools"


def load_scanner(name):
    # The command scripts execute at module scope; test their real function AST
    # without executing a customer's workspace command as an import side effect.
    tree = ast.parse((TOOLS / name).read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "iter_n_regions")
    imports = [node for node in tree.body if isinstance(node, ast.Import)
               and any(alias.name == "re" for alias in node.names)]
    namespace = {}
    exec(compile(ast.Module(body=[*imports, function], type_ignores=[]), name, "exec"), namespace)
    return namespace["iter_n_regions"]


def legacy(sequence):
    index = 0
    while index < len(sequence):
        if sequence[index] not in {"N", "n"}:
            index += 1
            continue
        start = index
        while index < len(sequence) and sequence[index] in {"N", "n"}:
            index += 1
        yield start + 1, index, index - start


class NRegionScanTests(unittest.TestCase):
    def setUp(self):
        self.scanners = [load_scanner(name) for name in ("assign_chr_groups.py", "add_ctg_stage.py")]

    def check(self, sequence):
        expected = list(legacy(sequence))
        for scan in self.scanners:
            self.assertEqual(list(scan(sequence)), expected, repr(sequence[:80]))

    def test_empty_no_n_and_edge_runs(self):
        for value in ("", "ACGTacgt", "N", "n", "NnNn", "nACGTN", "ANnNCnnG", "N-?n", "éNn𐀀n"):
            self.check(value)

    def test_exhaustive_short_sequences(self):
        for length in range(8):
            for chars in itertools.product("ANn", repeat=length):
                self.check("".join(chars))

    def test_deterministic_random_sequences(self):
        rng = random.Random(20261118)
        for _ in range(200):
            self.check("".join(rng.choices("ACGTacgtNn-", k=rng.randrange(3000))))

    def test_long_runs_and_sparse_gaps(self):
        for sequence in ("ACGT" * 100000, "Nn" * 100000,
                         "a" * 100003 + "N" * 99 + "n" + "c" * 120005 + "nN"):
            self.check(sequence)

    def test_coordinate_convention(self):
        for scan in self.scanners:
            self.assertEqual(list(scan("ANNnCNN")), [(2, 4, 3), (6, 7, 2)])


if __name__ == "__main__":
    unittest.main()
