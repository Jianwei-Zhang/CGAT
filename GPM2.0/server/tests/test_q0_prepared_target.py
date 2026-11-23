from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from server.tools.lgz_core.common import executable_identity
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.q0_sources import SourceKey,split_source,Q0EvidenceError
from server.tools.lgz_core import q0_preparation as prep


class PreparedTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        sources={SourceKey('ds',name):'ACGT'*1000 for name in ('a','b','c')}
        parts={p.segment_id:p for key,seq in sources.items() for p in split_source(key,seq).segments}
        self.catalog=CandidateCatalog({'candidates':[]},sources,parts)
        self.ids={p.source.contig:key for key,p in parts.items()}
        tool=self.root/'mapper.py';tool.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\nif "--version" in sys.argv: print("synthetic-native-mapper")\nelse: Path(sys.argv[sys.argv.index("-o")+1]).write_text("")\n');tool.chmod(0o755)
        self.tool=executable_identity(str(tool))
        self.targets=sorted([self.ids['b'],self.ids['c']])
        request={'kind':'unplaced_discovery','query_ids':[self.ids['a']],'target_ids':self.targets}
        self.original=prep._supplement(self.root,self.catalog,request,self.tool,'asm10',1)
        self.template={'root':str(self.root),'receipt':prep.identity(self.root,self.original['receipt'])}
        self.original_target=(self.root/self.original['paf']).with_name('target.fa')

    def test_copied_verified_target_does_not_require_second_whole_genome_heap(self):
        new=self.root/'isolated';new.mkdir()
        query=self.ids['c'];source=self.catalog.parts[query].source
        partial=CandidateCatalog({'candidates':[]},{source:self.catalog.sequences[source]},self.catalog.parts)
        request={'kind':'candidate_unroutable_seed','query_ids':[query],'target_ids':self.targets}
        task=prep._supplement(new,partial,request,self.tool,'asm10',1,prepared_target=self.template)
        target=(new/task['paf']).with_name('target.fa')
        self.assertEqual(target.read_bytes(),self.original_target.read_bytes())
        self.assertNotEqual(target.stat().st_ino,self.original_target.stat().st_ino)
        command=json.loads((target.parent/'command.json').read_text())
        self.assertEqual(command['prepared_target_reuse']['source_receipt_identity'],self.template['receipt'])
        with mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('complete native cache must reuse')):
            self.assertEqual(prep._supplement(new,partial,request,self.tool,'asm10',1),task)

    def test_different_members_or_target_inventory_are_rejected(self):
        target=self.root/'copy.fa'
        with self.assertRaises(Q0EvidenceError):prep._copy_prepared_target(self.root,self.catalog,[self.ids['c']],target,self.template)
        self.assertFalse(target.exists())

    def test_corruption_and_mutation_during_copy_are_not_certified(self):
        target=self.root/'copy.fa';copy=prep.shutil.copyfile
        def changing(source,destination):
            result=copy(source,destination);source.write_bytes(source.read_bytes()+b'\n');return result
        with mock.patch.object(prep.shutil,'copyfile',side_effect=changing):
            with self.assertRaises(Q0EvidenceError):prep._copy_prepared_target(self.root,self.catalog,self.targets,target,self.template)
        with self.assertRaises(Q0EvidenceError):prep._copy_prepared_target(self.root,self.catalog,self.targets,self.root/'another.fa',self.template)

    def test_identity_memo_does_not_accept_same_size_edit_with_restored_mtime(self):
        path=self.root/"identity.txt";path.write_text("AAAA")
        before=prep.identity(self.root,"identity.txt");stat=path.stat()
        path.write_text("BBBB");os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        after=prep.identity(self.root,"identity.txt")
        self.assertEqual(before["size"],after["size"]);self.assertNotEqual(before["sha256"],after["sha256"])

    def test_existing_wrong_destination_is_preserved_not_silently_overwritten(self):
        target=self.root/'copy.fa';target.write_text('broken')
        prep._copy_prepared_target(self.root,self.catalog,self.targets,target,self.template)
        self.assertEqual(target.read_bytes(),self.original_target.read_bytes())
        backups=list(self.root.glob('copy.fa.invalid-*'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),'broken')


if __name__=='__main__':unittest.main()
