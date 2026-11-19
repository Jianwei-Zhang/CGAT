"""Compose immutable self profiles without rekeying completed primary batches.

Only explicit, hash-bound execution runtimes are loaded. No code or profile is
rewritten. The extension must use the same native inputs and disjoint batches.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import full_self_seed_pilot as pilot

SCHEMA = "incident_self_composite_profile_v1"
RECEIPT = "self-profile-receipt.json"
OUTPUTS = ("raw.paf", "result.paf", "stderr.log")
_MODULES = {}


def checked(row):
    path = Path(row["path"]).resolve(strict=True)
    if pilot.digest(path) != row["sha256"]:
        raise ValueError("self profile dependency changed: " + str(path))
    return path


def Profile(path):
    path = Path(path).resolve(strict=True)
    spec = json.loads(path.read_text())
    if spec.get("schema") == SCHEMA:
        return CompositeProfile(path)
    if spec.get("schema") not in ("incident_self_seed_profile_v1", "incident_self_seed_profile_extended_v1"):
        raise ValueError("unsupported self profile schema")
    source = checked(spec["dependencies"]["runtime"])
    if source == Path(__file__).resolve():
        raise ValueError("leaf profile cannot bind composite runtime")
    key = (str(source), spec["dependencies"]["runtime"]["sha256"])
    if key not in _MODULES:
        # Reuse only an exact imported module, never a basename match.
        module = next((m for m in list(sys.modules.values())
                       if getattr(m, "__file__", None)
                       and Path(m.__file__).resolve() == source), None)
        if module is None:
            loader = importlib.util.spec_from_file_location("incident_self_leaf_" + key[1], source)
            module = importlib.util.module_from_spec(loader)
            loader.loader.exec_module(module)
        _MODULES[key] = module
    return _MODULES[key].Profile(path)


class CompositeProfile:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.sha = pilot.digest(self.path)
        self.spec = json.loads(self.path.read_text())
        if self.spec.get("schema") != SCHEMA:
            raise ValueError("wrong composite profile schema")
        if checked(self.spec["runtime"]) != Path(__file__).resolve():
            raise ValueError("unbound composite profile runtime")
        primary_path = checked(self.spec["primary_profile"])
        extension_path = checked(self.spec["extension_profile"])
        if self.path in (primary_path, extension_path) or primary_path == extension_path:
            raise ValueError("cyclic or duplicate composite inputs")
        if any(json.loads(p.read_text()).get("schema") == SCHEMA for p in (primary_path, extension_path)):
            raise ValueError("nested composite profiles are not supported")
        self.primary = Profile(primary_path)
        self.extension = Profile(extension_path)
        if self.extension.spec["schema"] != "incident_self_seed_profile_extended_v1":
            raise ValueError("extension must bind the explicit extended runtime")
        if (self.primary.native != self.extension.native
                or self.primary.work != self.extension.work
                or self.primary.source != self.extension.source
                or self.primary.policy["seed_fraction"] != self.extension.policy["seed_fraction"]
                or set(self.primary.selected) & set(self.extension.selected)
                or not self.extension.selected):
            raise ValueError("overlapping or scientifically incompatible self profiles")
        self.work, self.source = self.primary.work, self.primary.source
        if self.path.is_relative_to(self.work) or self.spec["workspace"] != str(self.work):
            raise ValueError("composite profile must be isolated from the analysis workspace")
        if self.spec["native_manifest"] != self.primary.spec["native_manifest"]:
            raise ValueError("composite native manifest differs")
        self.native = self.primary.native
        self.manifest = copy.deepcopy(self.primary.manifest)
        for i in self.extension.selected:
            self.manifest["batches"][i] = copy.deepcopy(self.extension.manifest["batches"][i])
        self.selected = sorted(set(self.primary.selected) | set(self.extension.selected))
        # Admission uses seed_fraction. Audits must read each owner's policy.
        self.policy = self.extension.policy
        self.helper, self.contract = self.primary.helper, self.primary.contract
        self.verify()

    def verify(self):
        if pilot.digest(self.path) != self.sha:
            raise ValueError("composite profile changed")
        for field in ("runtime", "primary_profile", "extension_profile"):
            checked(self.spec[field])
        self.primary.verify()
        self.extension.verify()

    def owner(self, index):
        return self.extension if index in self.extension.selected else self.primary

    def validate_batch(self, index):
        return self.owner(index).validate_batch(index)

    @property
    def merge_manifest_path(self):
        return self.path

    @property
    def merge_manifest_sha(self):
        return self.sha

    def merge(self):
        self.verify()
        if any(not (Path(b["directory"]) / "complete.json").is_file() for b in self.manifest["batches"]):
            return False
        if not all(self.validate_batch(i) for i in range(len(self.manifest["batches"]))):
            raise ValueError("composite self batch receipt/output mismatch before merge")
        merged = self.helper.merge_if_complete(self.path, self.manifest)
        self.verify()
        return merged
