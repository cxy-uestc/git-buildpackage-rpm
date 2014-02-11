# vim: set fileencoding=utf-8 :
#
# (C) 2013 Intel Corporation <markus.lehtonen@linux.intel.com>
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""Tests for the gbp pq-rpm tool"""

import os
import tempfile
from nose.tools import assert_raises, eq_, ok_ # pylint: disable=E0611

from gbp.scripts.pq_rpm import main as pq
from gbp.git import GitRepository
from gbp.command_wrappers import GitCommand

from tests.component.rpm import RpmRepoTestBase

# Disable "Method could be a function warning"
# pylint: disable=R0201


def mock_pq(args):
    """Wrapper for pq"""
    # Call pq-rpm with added arg0
    return pq(['arg0'] + args)

class TestPqRpm(RpmRepoTestBase):
    """Basic tests for gbp-pq-rpm"""

    def test_invalid_args(self):
        """See that pq-rpm fails gracefully when called with invalid args"""
        GitRepository.create('.')
        # Test empty args
        eq_(mock_pq([]), 1)
        self._check_log(0, 'gbp:error: No action given.')
        self._clear_log()

        # Test invalid command
        eq_(mock_pq(['mycommand']), 1)
        self._check_log(0, "gbp:error: Unknown action 'mycommand'")
        self._clear_log()

        # Test invalid cmdline options
        with assert_raises(SystemExit):
            mock_pq(['--invalid-arg=123'])

    def test_import_outside_repo(self):
        """Run pq-rpm when not in a git repository"""
        eq_(mock_pq(['export']), 1)
        self._check_log(0, 'gbp:error: %s is not a git repository' %
                              os.path.abspath(os.getcwd()))

    def test_invalid_config_file(self):
        """Test invalid config file"""
        # Create dummy invalid config file and run pq-rpm
        GitRepository.create('.')
        with open('.gbp.conf', 'w') as conffd:
            conffd.write('foobar\n')
        eq_(mock_pq(['foo']), 1)
        self._check_log(0, 'gbp:error: Invalid config file: File contains no '
                           'section headers.')

    def test_import_export(self):
        """Basic test for patch import and export"""
        repo = self.init_test_repo('gbp-test')
        branches = repo.get_local_branches() + ['development/master']
        # Test import
        eq_(mock_pq(['import']), 0)
        files = ['AUTHORS', 'dummy.sh', 'Makefile', 'NEWS', 'README', 'mydir/',
                 'mydir/myfile.txt', '.gbp.conf']
        branches.append('development/master')
        self._check_repo_state(repo, 'development/master', branches, files)
        eq_(repo.get_merge_base('upstream', 'development/master'),
            repo.rev_parse('upstream'))
        ok_(len(repo.get_commits('', 'upstream')) <
            len(repo.get_commits('', 'development/master')))

        # Test export
        eq_(mock_pq(['export']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 '0001-my-gz.patch', '0002-my-bzip2.patch', '0003-my2.patch',
                 'my.patch']
        self._check_repo_state(repo, 'master', branches, files)
        eq_(repo.status()[' M'], ['gbp-test.spec'])

        # Another export after removing some patches
        os.unlink('0001-my-gz.patch')
        eq_(mock_pq(['export']), 0)
        self._check_repo_state(repo, 'master', branches, files)

    def test_import_export2(self):
        """Another test for import and export"""
        repo = self.init_test_repo('gbp-test2')
        branches = repo.get_local_branches() + ['development/master-orphan']
        repo.set_branch('master-orphan')
        # Import
        eq_(mock_pq(['import']), 0)
        files = ['dummy.sh', 'Makefile', 'README', 'mydir/',
                 'mydir/myfile.txt', '.gbp.conf']
        self._check_repo_state(repo, 'development/master-orphan', branches,
                               files)

        # Test export
        eq_(mock_pq(['export']), 0)
        self._check_repo_state(repo, 'master-orphan', branches)
        eq_(repo.status()[' M'], ['packaging/gbp-test2.spec'])

    def test_import_in_subdir(self):
        """Test running gbp-rpm-pq from a subdir in the git tree"""
        repo = self.init_test_repo('gbp-test2')
        repo.set_branch('master-orphan')
        branches = repo.get_local_branches() + ['development/master-orphan']
        os.chdir('packaging')

        # Running from subdir should be ok
        eq_(mock_pq(['import']), 0)
        self._check_repo_state(repo, 'development/master-orphan', branches)


    def test_rebase(self):
        """Basic test for rebase action"""
        repo = self.init_test_repo('gbp-test')
        branches = repo.get_local_branches() + ['development/master']
        # Import and make development branch out-of-sync
        eq_(mock_pq(['import']), 0)
        GitCommand("rebase")(['--onto', 'upstream^', 'upstream'])
        # Sanity check for our git rebase...
        ok_(repo.get_merge_base('development/master', 'upstream') !=
            repo.rev_parse('upstream'))

        # Do rebase
        eq_(mock_pq(['rebase']), 0)
        self._check_repo_state(repo, 'development/master', branches)
        ok_(repo.get_merge_base('development/master', 'upstream') ==
            repo.rev_parse('upstream'))

        # Get to out-of-sync, again, and try rebase from master branch
        GitCommand("rebase")(['--onto', 'upstream^', 'upstream'])
        eq_(mock_pq(['switch']), 0)
        eq_(mock_pq(['rebase']), 0)
        self._check_repo_state(repo, 'development/master', branches)
        ok_(repo.get_merge_base('development/master', 'upstream') ==
            repo.rev_parse('upstream'))

    def test_switch(self):
        """Basic test for switch action"""
        repo = self.init_test_repo('gbp-test')
        pkg_files = repo.list_files()
        branches = repo.get_local_branches() + ['development/master']
        upstr_files = ['dummy.sh', 'Makefile', 'README']
        # Switch to pq branch
        eq_(mock_pq(['switch']), 0)
        self._check_repo_state(repo, 'development/master', branches,
                               upstr_files)

        # Switch back to packaging branch
        eq_(mock_pq(['switch']), 0)
        self._check_repo_state(repo, 'master', branches, pkg_files)

    def test_switch_drop(self):
        """Basic test for drop action"""
        repo = self.init_test_repo('gbp-test')
        init_branches = repo.get_local_branches()
        # Import
        eq_(mock_pq(['import']), 0)
        branches = init_branches + ['development/master']
        self._check_repo_state(repo, 'development/master', branches)

        # Drop pq should fail when on pq branch
        eq_(mock_pq(['drop']), 1)
        self._check_log(-1, "gbp:error: On a patch-queue branch, can't drop it")
        self._check_repo_state(repo, 'development/master', branches)

        # Switch to master
        eq_(mock_pq(['switch']), 0)
        self._check_repo_state(repo, 'master', branches)

        # Drop should succeed when on master branch
        eq_(mock_pq(['drop']), 0)
        self._check_repo_state(repo, 'master', init_branches)

    def test_force_import(self):
        """Test force import"""
        repo = self.init_test_repo('gbp-test')
        pkg_files = repo.list_files()
        branches = repo.get_local_branches() + ['development/master']
        # Import
        eq_(mock_pq(['import']), 0)
        pq_files = ['AUTHORS', 'dummy.sh', 'Makefile', 'NEWS', 'README',
                    'mydir/', 'mydir/myfile.txt', '.gbp.conf']
        branches.append('development/master')
        self._check_repo_state(repo, 'development/master', branches, pq_files)

        # Re-import should fail
        eq_(mock_pq(['import']), 1)
        self._check_log(-1, "gbp:error: Already on a patch-queue branch")
        self._check_repo_state(repo, 'development/master', branches, pq_files)

        # Mangle pq branch and try force import on top of that
        repo.force_head('master', hard=True)
        self._check_repo_state(repo, 'development/master', branches, pkg_files)
        eq_(mock_pq(['import', '--force']), 0)
        self._check_repo_state(repo, 'development/master', branches, pq_files)

        # Switch back to master
        eq_(mock_pq(['switch']), 0)
        self._check_repo_state(repo, 'master', branches, pkg_files)

        # Import should fail
        eq_(mock_pq(['import']), 1)
        self._check_log(-1, "gbp:error: Patch-queue branch .* already exists")
        self._check_repo_state(repo, 'master', branches, pkg_files)

        # Force import should succeed
        eq_(mock_pq(['import', '--force']), 0)
        self._check_repo_state(repo, 'development/master', branches, pq_files)

    def test_apply(self):
        """Basic test for apply action"""
        repo = self.init_test_repo('gbp-test')
        upstr_files = ['dummy.sh', 'Makefile', 'README']
        branches = repo.get_local_branches() + ['development/master']

        # No patch given
        eq_(mock_pq(['apply']), 1)
        self._check_log(-1, "gbp:error: No patch name given.")

        # Apply patch
        with tempfile.NamedTemporaryFile() as tmp_patch:
            tmp_patch.write(repo.show('master:%s' % 'my.patch'))
            tmp_patch.file.flush()
            eq_(mock_pq(['apply', tmp_patch.name]), 0)
            self._check_repo_state(repo, 'development/master', branches,
                                   upstr_files)

        # Apply another patch, now when already on pq branch
        with tempfile.NamedTemporaryFile() as tmp_patch:
            tmp_patch.write(repo.show('master:%s' % 'my2.patch'))
            tmp_patch.file.flush()
            eq_(mock_pq(['apply', tmp_patch.name]), 0)
        self._check_repo_state(repo, 'development/master', branches,
                               upstr_files + ['mydir/', 'mydir/myfile.txt'])

    def test_convert(self):
        """Basic test for convert action"""
        repo = self.init_test_repo('gbp-test2')
        branches = repo.get_local_branches() + ['master-orphan']
        files = ['packaging/', 'packaging/bar.tar.gz', 'packaging/foo.txt',
                 'packaging/gbp-test2.spec', 'packaging/gbp-test2-alt.spec',
                 'packaging/my.patch', 'packaging/0001-My-addition.patch',
                 '.gbp.conf']
        # First should fail because 'master-orphan' branch already exists
        eq_(mock_pq(['convert']), 1)
        self._check_log(-1, "gbp:error: Branch 'master-orphan' already exists")

        # Re-try with force
        eq_(mock_pq(['convert', '--force']), 0)
        self._check_repo_state(repo, 'master-orphan', branches, files)

    def test_convert_fail(self):
        """Tests for convert action error cases"""
        repo = self.init_test_repo('gbp-test')
        branches = repo.get_local_branches()

        # Already on orphan packaging branch
        eq_(mock_pq(['convert']), 1)
        self._check_repo_state(repo, 'master', branches)
        self._check_log(-1, ".*is not based on upstream version")

        # Create a pq branch and try from there
        eq_(mock_pq(['import']), 0)
        eq_(mock_pq(['convert']), 1)
        self._check_repo_state(repo, 'development/master',
                               branches + ['development/master'])
        self._check_log(-1, ".*you're on patch-queue branch")

        # Switch back to orphan packaging branch and try again
        eq_(mock_pq(['switch']), 0)
        eq_(mock_pq(['convert']), 1)
        self._check_repo_state(repo, 'master',
                               branches + ['development/master'])
        self._check_log(-1, r".*pq branch \S+ already exists")

    def test_option_patch_numbers(self):
        """Test the --patch-numbers cmdline option"""
        repo = self.init_test_repo('gbp-test')
        branches = repo.get_local_branches() + ['development/master']
        eq_(mock_pq(['import']), 0)
        # Export
        eq_(mock_pq(['export', '--no-patch-numbers']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 'my-gz.patch', 'my-bzip2.patch', 'my2.patch',
                 'my.patch']
        self._check_repo_state(repo, 'master', branches, files)

    def test_option_tmp_dir(self):
        """Test the --tmp-dir cmdline option"""
        self.init_test_repo('gbp-test')
        eq_(mock_pq(['import', '--tmp-dir=foo/bar']), 0)
        # Check that the tmp dir basedir was created
        ok_(os.path.isdir('foo/bar'))

    def test_option_upstream_tag(self):
        """Test the --upstream-tag cmdline option"""
        repo = self.init_test_repo('gbp-test')

        # Non-existent upstream-tag -> failure
        eq_(mock_pq(['import', '--upstream-tag=foobar/%(upstreamversion)s']), 1)
        self._check_log(-1, "gbp:error: Couldn't find upstream version")

        # Create tag -> import should succeed
        repo.create_tag('foobar/1.1', msg="test tag", commit='upstream')
        eq_(mock_pq(['import', '--upstream-tag=foobar/%(upstreamversion)s']), 0)

    def test_option_spec_file(self):
        """Test --spec-file commandline option"""
        self.init_test_repo('gbp-test')

        # Non-existent spec file should lead to failure
        eq_(mock_pq(['import', '--spec-file=foo.spec']), 1)
        self._check_log(-1, "gbp:error: Can't parse spec: Unable to read spec")
        # Correct spec file
        eq_(mock_pq(['import', '--spec-file=gbp-test.spec']), 0)

        # Force import on top to test parsing spec from another branch
        eq_(mock_pq(['import', '--spec-file=gbp-test.spec', '--force']), 0)

        # Test with export, too
        eq_(mock_pq(['export', '--spec-file=foo.spec']), 1)
        self._check_log(-1, "gbp:error: Can't parse spec: Unable to read spec")
        eq_(mock_pq(['export', '--spec-file=gbp-test.spec']), 0)

    def test_option_packaging_dir(self):
        """Test --packaging-dir command line option"""
        self.init_test_repo('gbp-test')

        # Wrong packaging dir should lead to failure
        eq_(mock_pq(['import', '--packaging-dir=foo']), 1)
        self._check_log(-1, "gbp:error: Can't parse spec: No spec file found")
        # Use correct packaging dir
        eq_(mock_pq(['import', '--packaging-dir=.']), 0)

        # Test with export, --spec-file option should override packaging dir
        eq_(mock_pq(['export', '--packaging-dir=foo',
                     '--spec-file=gbp-test.spec']), 0)

    def test_option_pq_branch(self):
        """Test the --pq-branch and --packaging-branch options"""
        repo = self.init_test_repo('gbp-test')

        # Invalid branch name
        eq_(mock_pq(['import', '--pq-branch=foo:']), 1)
        self._check_log(-1, "gbp:error: Cannot create patch-queue branch")
        eq_(mock_pq(['switch', '--pq-branch=foo:']), 1)
        self._check_log(-1, "gbp:error: Cannot create patch-queue branch")

        # Try all possible keys in pq-branch format string
        eq_(mock_pq(['import',
                     '--pq-branch=dev/%(branch)s/%(upstreamversion)s']), 0)
        branches = ['master', 'upstream', 'dev/master/1.1']
        self._check_repo_state(repo, 'dev/master/1.1', branches)

        # Switch to non-existent packaging branch should fail
        eq_(mock_pq(['switch', '--pq-branch=dev/master/1.1',
                     '--packaging-branch=foobar']), 1)
        self._check_log(-1, "gbp:error: Git command failed: Error running git")
        self._check_repo_state(repo, 'dev/master/1.1', branches)

        # Export to existing packaging branch should be ok
        eq_(mock_pq(['switch', '--pq-branch=dev/master/1.1',
                     '--packaging-branch=master']), 0)
        self._check_repo_state(repo, 'master', branches)

    def test_option_export_rev(self):
        """Test the --export-rev cmdline option"""
        repo = self.init_test_repo('gbp-test')
        eq_(mock_pq(['import']), 0)

        # Export directly from upstream -> no patches expected
        eq_(mock_pq(['export', '--export-rev=upstream']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 'my.patch']
        branches = ['master', 'upstream', 'development/master']
        self._check_repo_state(repo, 'master', branches, files)

        # Export another rev
        eq_(mock_pq(['export', '--export-rev=development/master~2']), 0)
        self._check_repo_state(repo, 'master', branches,
                               files + ['0001-my-gz.patch'])

        # Export from upstream..master should fail
        eq_(mock_pq(['export', '--export-rev=master']), 1)
        self._check_log(-1, "gbp:error: Start commit .* not an ancestor of end")
        # Export invalid rev should fail
        eq_(mock_pq(['export', '--export-rev=foobar']), 1)
        self._check_log(-1, "gbp:error: Invalid treeish object foobar")

        # Export plain treeish. Doesn't work in pq (at least) -
        # just for testing exception handling here
        content = repo.list_tree('development/master')
        tree = repo.make_tree(content)
        eq_(mock_pq(['export', '--export-rev=%s' % tree]), 1)
        self._check_log(-1, "gbp:error: Start commit .* not an ancestor of end")

    def test_option_patch_compress(self):
        """Test the --patch-export-compress cmdline option"""
        repo = self.init_test_repo('gbp-test')
        eq_(mock_pq(['import']), 0)

        # Export, all generated patches should be compressed
        eq_(mock_pq(['export', '--patch-export-compress=1']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 '0001-my-gz.patch.gz', '0002-my-bzip2.patch.gz',
                 '0003-my2.patch.gz', 'my.patch']
        branches = ['master', 'upstream', 'development/master']
        self._check_repo_state(repo, 'master', branches, files)

    def test_option_patch_export_squash(self):
        """Test the --patch-export-squash-until cmdline option"""
        repo = self.init_test_repo('gbp-test')
        eq_(mock_pq(['import']), 0)

        # Non-existent squash point should fail
        eq_(mock_pq(['export', '--patch-export-squash-until=foo']), 1)
        self._check_log(-1, r"gbp:error: Git command failed: revision 'foo\^0'")

        # Invalid squash point should fail
        eq_(mock_pq(['export', '--patch-export-squash-until=master']), 1)
        self._check_log(-1, "gbp:error: Given squash point 'master' not in the "
                            "history of end commit 'development/master'")

        # Squashing up to the second latest patch -> 1 "normal" patch
        squash = 'development/master~1'
        eq_(mock_pq(['export', '--patch-export-squash-until=%s' % squash]), 0)
        squash += ':squash'
        eq_(mock_pq(['export', '--patch-export-squash-until=%s' % squash]), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 'my.patch', 'squash.diff', '0002-my2.patch']
        branches = ['master', 'upstream', 'development/master']
        self._check_repo_state(repo, 'master', branches, files)

    def test_option_patch_export_ignore(self):
        """Test the --patch-export-ignore-path cmdline option"""
        repo = self.init_test_repo('gbp-test')

        eq_(mock_pq(['import']), 0)

        # Export
        eq_(mock_pq(['export', '--patch-export-ignore-path=mydir/.*']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 '0001-my-gz.patch', '0002-my-bzip2.patch', 'my.patch']
        branches = ['master', 'upstream', 'development/master']
        self._check_repo_state(repo, 'master', branches, files)

    def test_export_with_merges(self):
        """Test exporting pq-branch with merge commits"""
        repo = self.init_test_repo('gbp-test')
        # Import
        eq_(mock_pq(['import']), 0)

        # Create a merge commit in pq-branch
        patches = repo.format_patches('HEAD^', 'HEAD', '.')
        repo.force_head('HEAD^', hard=True)
        repo.commit_dir('.', 'Merge with master', 'development/master',
                        ['master'])
        merge_rev = repo.rev_parse('HEAD', short=7)
        eq_(mock_pq(['apply', patches[0]]), 0)
        upstr_rev = repo.rev_parse('upstream', short=7)
        os.unlink(patches[0])

        # Export should create diff up to the merge point and one "normal" patch
        eq_(mock_pq(['export']), 0)
        files = ['.gbp.conf', 'bar.tar.gz', 'foo.txt', 'gbp-test.spec',
                 'my.patch', '%s-to-%s.diff' % (upstr_rev, merge_rev),
                 '0002-my2.patch']
        branches = ['master', 'upstream', 'development/master']
        self._check_repo_state(repo, 'master', branches, files)

    def test_option_import_files(self):
        """Test the --import-files cmdline option"""
        repo = self.init_test_repo('gbp-test')
        # Add new conf file
        os.mkdir('debian')
        with open('debian/gbp.conf', 'w') as conf_file:
            conf_file.write('[DEFAULT]\npq-branch = my-pq-branch\n')
        repo.add_files(['debian/gbp.conf'], force=True)
        repo.commit_files(['debian/gbp.conf'], msg="Add conf file")

        # Import with default settings (should import gbp conf files)
        branches = repo.get_local_branches() + ['my-pq-branch']
        eq_(mock_pq(['import']), 0)
        self._check_repo_state(repo, 'my-pq-branch', branches)
        ok_('debian/gbp.conf' in repo.list_files())
        ok_('.gbp.conf' in repo.list_files())

        # Re-import with user-defined files
        eq_(mock_pq(['import', '--force', '--packaging-branch', 'master',
                     '--import-files', 'foo.txt,my.patch']), 0)
        self._check_repo_state(repo, 'my-pq-branch', branches)
        ok_('foo.txt' in repo.list_files())
        ok_('my.patch' in repo.list_files())

        # Drop and re-import with no files
        eq_(mock_pq(['switch', '--packaging-branch', 'master', '--pq-branch',
                     'my-pq-branch']), 0)
        eq_(mock_pq(['drop']), 0)
        eq_(mock_pq(['import', '--packaging-branch', 'master',
                     '--pq-branch', 'my-pq-branch', '--import-files=']), 0)
        self._check_repo_state(repo, 'my-pq-branch', branches)
        ok_('debian/gbp.conf' not in repo.list_files())
        ok_('.gbp.conf' not in repo.list_files())

    def test_option_new_packaging_dir(self):
        """Test the --new-packaging-dir cmdline option"""
        repo = self.init_test_repo('gbp-test2')
        branches = repo.get_local_branches() + ['master-orphan']
        files = ['rpm/', 'rpm/bar.tar.gz', 'rpm/foo.txt',
                 'rpm/gbp-test2.spec', 'rpm/gbp-test2-alt.spec',
                 'rpm/my.patch', 'rpm/0001-My-addition.patch']
        # Drop already-existing master-orphan branch
        repo.delete_branch('master-orphan')
        # Try convert
        eq_(mock_pq(['convert', '--import-files=',
                     '--new-packaging-dir=rpm']), 0)
        self._check_repo_state(repo, 'master-orphan', branches, files)

    def test_import_unapplicable_patch(self):
        """Test import when a patch does not apply"""
        repo = self.init_test_repo('gbp-test')
        branches = repo.get_local_branches()
        # Mangle patch
        with open('my2.patch', 'w') as patch_file:
            patch_file.write('-this-does\n+not-apply\n')
        eq_(mock_pq(['import']), 1)
        self._check_log(-1, "("
                             "Aborting|"
                             "Please, commit your changes or stash them|"
                             "gbp:error: Import failed.* You have local changes"
                            ")")
        self._check_repo_state(repo, 'master', branches)

        # Now commit the changes to the patch and try again
        repo.add_files(['my2.patch'], force=True)
        repo.commit_files(['my2.patch'], msg="Mangle patch")
        eq_(mock_pq(['import']), 1)
        self._check_log(-1, "gbp:error: Import failed: Error running git apply")
        self._check_repo_state(repo, 'master', branches)

