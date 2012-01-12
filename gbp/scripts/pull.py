# vim: set fileencoding=utf-8 :
#
# (C) 2009,2013 Guido Guenther <agx@sigxcpu.org>
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
#
# heavily inspired by dom-safe-pull which is © 2009 Stéphane Glondu <steph@glondu.net>
#
"""fast forward debian, upstream and pristine-tar branch"""

import ConfigParser
import sys
import os, os.path
from gbp.command_wrappers import (Command, CommandExecFailed)
from gbp.config import (GbpOptionParser, GbpOptionGroup)
from gbp.errors import GbpError
from gbp.git import GitRepositoryError
from gbp.deb.git import DebianGitRepository
import gbp.log

def update_branch(branch, repo, options):
    """
    update branch to its remote branch, fail on non fast forward updates
    unless --force is given
    @return: branch updated or already up to date
    @rtype: boolean
    """
    update = None

    remote = repo.get_merge_branch(branch)
    if not remote:
        gbp.log.warn("No branch tracking '%s' found - skipping." % branch)
        return False

    can_fast_forward, up_to_date = repo.is_fast_forward(branch, remote)

    if up_to_date: # Great, we're done
        gbp.log.info("Branch '%s' is already up to date." % branch)
        return True

    if can_fast_forward:
        update = 'merge'
    else:
        if options.force == 'merge':
            gbp.log.info("Non-fast forwarding '%s' due to --force=merge" % branch)
            update = 'merge'
        elif options.force == 'clean':
            gbp.log.info("Checking out clean copy of '%s' due to --force=clean" % branch)
            update = 'clean'
        else:
            gbp.log.warn("Skipping non-fast forward of '%s' - use --force or "
                         "update manually" % branch)

    if update:
        gbp.log.info("Updating '%s'" % branch)
        if repo.branch == branch:
            if update == 'merge':
                repo.merge(remote)
            elif update == 'clean':
                # Have to drop our current branch
                tmpbranch = "_gbptmp-"+branch
                gbp.log.debug("Checking out '%s' to '%s'" % (remote, tmpbranch))
                repo.create_branch(tmpbranch, remote)
                gbp.log.debug("Switching current branch to '%s'" % (tmpbranch))
                repo.set_branch(tmpbranch)
                gbp.log.debug("Dropping branch '%s'" % branch)
                repo.delete_branch(branch)
                gbp.log.info("Renaming branch '%s' to '%s'" % (tmpbranch, branch))
                repo.rename_branch(tmpbranch, branch)
        else:
            if can_fast_forward or (update == 'clean'):
                sha1 = repo.rev_parse(remote)
                repo.update_ref("refs/heads/%s" % branch, sha1,
                                msg="gbp: forward %s to %s" % (branch, remote))
            elif update == 'merge':
                # Merge other branch, if it cannot be fast-forwarded
                current_branch=repo.branch
                repo.set_branch(branch)
                repo.merge(remote)
                repo.set_branch(current_branch)

    return (update != None)


def build_parser(name):
    try:
        parser = GbpOptionParser(command=os.path.basename(name), prefix='',
                             usage='%prog [options] - safely update a repository from remote')
    except ConfigParser.ParsingError as err:
        gbp.log.err(err)
        return None

    branch_group = GbpOptionGroup(parser, "branch options", "branch update and layout options")
    parser.add_option_group(branch_group)
    branch_group.add_boolean_config_file_option(option_name = "ignore-branch", dest="ignore_branch")
    branch_group.add_option("--force", action="store", dest="force",
                      default=None,
                      help="force a branch update even if it can't be fast "
                           "forwarded (valid ACTIONs are 'merge', 'clean')",
                      metavar='ACTION')
    branch_group.add_option("--all", action="store_true", default=False,
                            help="update all remote-tracking branches that "
                                 "have identical name in the remote")
    branch_group.add_option("--redo-pq", action="store_true", dest="redo_pq", default=False,
                      help="redo the patch queue branch after a pull. Warning: this drops the old patch-queue branch")
    branch_group.add_config_file_option(option_name="upstream-branch", dest="upstream_branch")
    branch_group.add_config_file_option(option_name="debian-branch", dest="debian_branch")
    branch_group.add_boolean_config_file_option(option_name="pristine-tar", dest="pristine_tar")
    branch_group.add_option("--depth", action="store", dest="depth", default=0,
                            help="git history depth (for deepening shallow clones)")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False,
                      help="verbose command execution")
    parser.add_config_file_option(option_name="color", dest="color", type='tristate')
    parser.add_config_file_option(option_name="color-scheme",
                                  dest="color_scheme")
    return parser


def parse_args(argv):
    parser = build_parser(argv[0])
    if not parser:
        return None, None
    return parser.parse_args(argv)


def main(argv):
    retval = 0
    current = None

    (options, args) = parse_args(argv)
    if not options:
        return 1

    gbp.log.setup(options.color, options.verbose, options.color_scheme)

    try:
        repo = DebianGitRepository(os.path.curdir)
    except GitRepositoryError:
        gbp.log.err("%s is not a git repository" % (os.path.abspath('.')))
        return 1

    try:
        branches = set()
        try:
            current = repo.get_branch()
        except GitRepositoryError:
            # Not being on any branch is o.k. with --git-ignore-branch
            if  options.ignore_branch:
                current = repo.head
                gbp.log.info("Found detached head at '%s'" % current)
            else:
                raise

        for branch in [ options.debian_branch, options.upstream_branch ]:
            if repo.has_branch(branch):
                branches.add(branch)

        if repo.has_pristine_tar_branch() and options.pristine_tar:
            branches.add(repo.pristine_tar_branch)

        if options.all:
            current_remote = repo.get_merge_branch(current)
            if current_remote:
                fetch_remote = current_remote.split('/')[0]
            else:
                fetch_remote = 'origin'
            for branch in repo.get_local_branches():
                merge_branch = repo.get_merge_branch(branch)
                if merge_branch:
                    rem, rem_br = merge_branch.split('/', 1)
                    if rem == fetch_remote and branch == rem_br:
                        branches.add(branch)

        (ret, out) = repo.is_clean()
        if not ret:
            gbp.log.err("You have uncommitted changes in your source tree:")
            gbp.log.err(out)
            raise GbpError

        repo.fetch(depth=options.depth)
        repo.fetch(depth=options.depth, tags=True)
        for branch in branches:
            if not update_branch(branch, repo, options):
                retval = 2

        if options.redo_pq:
            repo.set_branch(options.debian_branch)
            Command("gbp-pq")(["drop"])
            Command("gbp-pq")(["import"])

        repo.set_branch(current)
    except CommandExecFailed:
        retval = 1
    except (GbpError, GitRepositoryError) as err:
        if len(err.__str__()):
            gbp.log.err(err)
        retval = 1

    return retval

if __name__ == '__main__':
    sys.exit(main(sys.argv))

# vim:et:ts=4:sw=4:et:sts=4:ai:set list listchars=tab\:»·,trail\:·:
