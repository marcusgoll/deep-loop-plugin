import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from candidate_snapshot import capture_candidate
from git_candidate_export import GitCandidateExport, RULES, git_object

class GitExportTests(unittest.TestCase):
    def setUp(self):
        if sys.platform!='linux':
            mount=patch('candidate_snapshot._mount_id',return_value=1);mount.start();self.addCleanup(mount.stop)
            export_mount=patch('git_candidate_export._mount_id',return_value=1);export_mount.start();self.addCleanup(export_mount.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.policy={'schema':1,'candidate_root':str(self.root),'scope':'entire_candidate','allowed_uids':[os.getuid()],
                     'max_entries':100,'max_file_bytes':4096,'max_total_bytes':16384,'max_depth':6}
        (self.root/'source.txt').write_bytes(b'complete source\n')
    def exporter(self):return GitCandidateExport(self.policy,capture_candidate(self.policy),RULES.copy())
    def test_real_git_hashes_modes_nested_names_and_empty_directories(self):
        if not shutil.which('git'):self.skipTest('Requires independent Git object oracle')
        (self.root/'empty').mkdir();(self.root/'.hidden').write_bytes(b'\0binary\xff')
        (self.root/'a').mkdir();(self.root/'a'/'path').write_text('directory child named path')
        (self.root/'a.c').write_text('sorting peer');(self.root/'run.sh').write_text('#!/bin/sh\n');(self.root/'run.sh').chmod(0o700)
        exporter=self.exporter();plan=exporter.plan();files={row['path']:row for row in plan['files']}
        self.assertEqual(set(files),{'source.txt','.hidden','a/path','a.c','run.sh'});self.assertEqual(files['run.sh']['mode'],'100755')
        self.assertEqual(files['source.txt']['mode'],'100644')
        gitdir=self.root.parent/(self.root.name+'-git-oracle');gitdir.mkdir();self.addCleanup(shutil.rmtree,gitdir)
        env={'PATH':os.defpath,'HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.hooksPath','GIT_CONFIG_VALUE_0':'/dev/null'}
        subprocess.run(['git','init','--bare',str(gitdir)],env=env,capture_output=True,check=True)
        for row in plan['files']:
            data=exporter.read_blob(plan,row['sha'])
            actual=subprocess.run(['git','--git-dir='+str(gitdir),'hash-object','-w','--stdin'],env=env,input=data,capture_output=True,check=True).stdout.decode().strip()
            self.assertEqual(actual,row['sha'])
        for tree in plan['trees']:
            entries=b''.join((e['mode']+' '+e['type']+' '+e['sha']+'\t'+e['name']).encode()+b'\0' for e in tree['entries'])
            actual=subprocess.run(['git','--git-dir='+str(gitdir),'mktree','-z'],env=env,input=entries,capture_output=True,check=True).stdout.decode().strip()
            self.assertEqual(actual,tree['sha'])
        self.assertEqual(plan['trees'][-1]['sha'],plan['tree_sha'])
    def test_empty_complete_candidate_has_empty_git_tree(self):
        (self.root/'source.txt').unlink();plan=self.exporter().plan()
        self.assertEqual(plan['files'],[]);self.assertEqual(plan['tree_sha'],'4b825dc642cb6eb9a060e54bf8d69288fbee4904')
    def test_add_delete_and_mode_change_invalidate_old_plan(self):
        for kind in ('add','delete','mode'):
            with self.subTest(kind=kind):
                exporter=self.exporter();plan=exporter.plan();source=self.root/'source.txt'
                if kind=='add':(self.root/'new').write_text('new')
                elif kind=='delete':source.unlink()
                else:source.chmod(0o700)
                with self.assertRaises(ValueError):exporter.read_blob(plan,plan['files'][0]['sha'])
                for p in self.root.iterdir():p.unlink()
                source.write_bytes(b'complete source\n');source.chmod(0o600)
    def test_projection_policy_cannot_select_subsets_or_omit_modes(self):
        for rule in ({}, {**RULES,'exclude':['secret']},{**RULES,'file_modes':'all_regular'}):
            with self.assertRaises(ValueError):GitCandidateExport(self.policy,capture_candidate(self.policy),rule)
    def test_git_metadata_aliases_and_special_permissions_are_rejected(self):
        for name in ('.git','.GiT','.git.','.git '):
            p=self.root/name;p.mkdir()
            with self.assertRaisesRegex(ValueError,'Git metadata'):self.exporter().plan()
            p.rmdir()
        (self.root/'source.txt').chmod(0o4600)
        with self.assertRaisesRegex(ValueError,'permission'):self.exporter().plan()
    def test_changed_or_foreign_plan_and_unknown_blob_cannot_read(self):
        exporter=self.exporter();plan=exporter.plan();changed=copy.deepcopy(plan);changed['files'][0]['path']='outside'
        with self.assertRaises(ValueError):exporter.read_blob(changed,changed['files'][0]['sha'])
        with self.assertRaises(ValueError):exporter.read_blob(plan,'0'*40)
    def test_mount_boundary_and_midread_mutation_fail_closed(self):
        exporter=self.exporter()
        with patch('git_candidate_export._mount_id',side_effect=[1,2]):
            with self.assertRaises(ValueError):exporter.plan()
        original=os.read;changed=False
        def mutate(fd,count):
            nonlocal changed
            data=original(fd,count)
            if data and not changed:
                changed=True;(self.root/'source.txt').write_bytes(b'mutated during export')
            return data
        with patch('git_candidate_export.os.read',side_effect=mutate):
            with self.assertRaises(ValueError):exporter.plan()
    def test_binary_and_duplicate_blob_bytes_have_one_content_identity(self):
        data=b'\0\xffsame';(self.root/'source.txt').write_bytes(data);(self.root/'other').write_bytes(data)
        exporter=self.exporter();plan=exporter.plan();self.assertEqual(plan['files'][0]['sha'],plan['files'][1]['sha'])
        self.assertEqual(exporter.read_blob(plan,plan['files'][0]['sha']),data)
        self.assertEqual(git_object('blob',data),plan['files'][0]['sha'])
    def test_conflicting_source_bytes_with_same_git_blob_identity_are_rejected(self):
        (self.root/'other').write_bytes(b'different candidate bytes')
        exporter=self.exporter();read=exporter._read
        def collide(entry, **kwargs):
            _, data=read(entry, **kwargs)
            return 'a'*40, data
        with patch.object(exporter, '_read', side_effect=collide):
            with self.assertRaisesRegex(ValueError,'Conflicting candidate bytes'):
                exporter.plan()

if __name__=='__main__':unittest.main()
