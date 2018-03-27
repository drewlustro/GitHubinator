import codecs
import os
import re
import sublime
import sublime_plugin

# The urllib module has been split into parts and renamed in Python 3 to urllib.parse
try:
    from urllib.parse import quote, quote_plus
except ImportError:
    from urllib import quote, quote_plus


class GithubinatorCommand(sublime_plugin.TextCommand):
    """
    This will allow you to highlight your code, activate the plugin, then see the
    highlighted results on GitHub/Bitbucket.
    """
    DEFAULT_GIT_REMOTE = "origin"
    DEFAULT_HOST = "github.com"
    FORCE_BRANCH = False

    def load_config(self):
        s = sublime.load_settings("Githubinator.sublime-settings")
        self.default_remote = s.get("default_remote") or self.DEFAULT_GIT_REMOTE

        if not isinstance(self.default_remote, list):
            self.default_remote = [self.default_remote]

        self.default_host = s.get("default_host") or self.DEFAULT_HOST
        self.force_branch = s.get("force_branch") or self.FORCE_BRANCH

    def run(self, edit, copyonly=False, permalink=False, mode="blob", branch=None, open_repo=False):
        self.load_config()

        if not self.view.file_name():
            return

        # The current file
        full_name = os.path.realpath(self.view.file_name())
        folder_name, file_name = os.path.split(full_name)

        # Try to find a git directory
        git_path = self.recurse_dir(folder_name, ".git")
        if not git_path:
            sublime.status_message("Could not find .git directory.")
            return

        new_git_path = folder_name[len(git_path):]

        # path names normalize for UNC styling
        if os.name == "nt":
            new_git_path = new_git_path.replace("\\", "/")
            file_name = file_name.replace("\\", "/")

        # Read the config file in .git
        git_config_path = os.path.join(git_path, ".git", "config")
        with codecs.open(git_config_path, "r", "utf-8") as git_config_file:
            config = git_config_file.read()

        # Figure out the host
        scheme = "https"
        result = re.search(r"url.*?=.*?((https?)://([^/]*)/)|(git@([^:]*):)", config)
        if result:
            matches = result.groups()
            if matches[0]:
                scheme = matches[1]
                self.default_host = matches[2]
            else:
                self.default_host = matches[4]

        re_host = re.escape(self.default_host)

        if self.force_branch:
          branch = self.force_branch

        sha, current_branch = self.get_git_status(git_path)
        if not branch:
            branch = current_branch

        target = sha if permalink else branch
        target = quote_plus(target, safe="/")

        detected_remote = None
        regex = r".*\s.*(?:remote = )(\w+?)\r?\n"
        result = re.search(branch + regex, config)

        if result:
            matches = result.groups()
            detected_remote = [matches[0]]

        for remote in (detected_remote or self.default_remote):

            regex = r".*\s.*(?:https?://%s/|%s:|git://%s/)(.*)/(.*?)(?:\.git)?\r?\n" % (re_host, re_host, re_host)
            result = re.search(remote + regex, config)
            if not result:
                continue

            matches = result.groups()
            username = matches[0]
            project = matches[1]

            lines = self.get_selected_line_nums()

            repo_link = scheme + "://%s/%s/%s/" % (self.default_host, username, project)

            if open_repo:
                full_link = repo_link
            else:
                if "bitbucket" in self.default_host:
                    mode = "src" if mode == "blob" else "annotate"
                    lines = ":".join([str(l) for l in lines])
                    full_link = repo_link + "%s/%s%s/%s#cl-%s" % \
                        (mode, sha, new_git_path, file_name, lines)
                else:
                    lines = "-".join("L%s" % line for line in lines)
                    full_link = repo_link + "%s/%s%s/%s#%s" % \
                        (mode, target, new_git_path, file_name, lines)

            full_link = quote(full_link, safe=':/#@')

            sublime.set_clipboard(full_link)
            sublime.status_message("Copied %s to clipboard." % full_link)

            if not copyonly:
                self.view.window().run_command("open_url", {"url": full_link})

            break

    def get_selected_line_nums(self):
        """Get the line number of selections."""
        sel = self.view.sel()[0]
        begin_line = self.view.rowcol(sel.begin())[0] + 1
        end_line = self.view.rowcol(sel.end())[0] + 1

        if begin_line == end_line:
            lines = [begin_line]
        else:
            lines = [begin_line, end_line]

        return lines

    @staticmethod
    def get_git_status(git_path):
        """Get the current branch and SHA from git."""

        with open(os.path.join(git_path, ".git", "HEAD"), "r") as f:
            ref = f.read().replace("ref: ", "")[:-1]

        sha = None
        packed_ref_path = os.path.join(git_path, ".git", "packed-refs")

        if os.path.isfile(packed_ref_path):
            with codecs.open(packed_ref_path, "r", "utf-8") as f:
                regex = r"\s{0}(\s.*)?$".format(ref)
                try:
                    for line in f:
                        if re.search(regex, line):
                            sha = line.split(" ")[0]
                except UnicodeDecodeError:
                    None


        if not sha:
            with open(os.path.join(git_path, ".git", ref), "r") as f:
                sha = f.read()[:-1]

        branch = ref.replace("refs/heads/", "")

        return sha, branch

    def recurse_dir(self, path, folder):
        items = os.listdir(path)
        if folder in items and os.path.isdir(os.path.join(path, folder)):
            return path
        dirname = os.path.dirname(path)
        if dirname == path:
            return None
        return self.recurse_dir(dirname, folder)

    def is_enabled(self):
        if self.view.file_name() and len(self.view.file_name()) > 0:
            return True
        else:
            return False
