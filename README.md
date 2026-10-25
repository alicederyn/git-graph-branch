## git graph-branch

This tool provides a visual representation of the branches in your repository, including their relationships to upstream and merge branches.

### Quick Start

Install this tool using [uv][]:

[uv]: https://docs.astral.sh/uv/

```bash
$ uv tool install git+https://github.com/alicederyn/git-graph-branch.git
```

It will appear as a sub-command of `git`:

```bash
$ git graph-branch
```

### Help docs

```text
usage: git-graph-branch [-h] [--color] [--remote-icons] [--pr-icons] [-w] [--poll-every SECS]

Pretty-print branch metadata

options:
  -h, --help         show this help message and exit
  --color            Display colorized output; defaults to true if the output is a TTY and NO_COLOR is not set
  --remote-icons     Display remote status icon; defaults to true if the output is a TTY
  --pr-icons         Display PR check and review status icons; defaults to true if the output is a TTY

watch options:
  -w, --watch        Watch for changes and keep the graph updated
  --poll-every SECS  If watching, how often to poll for changes (default: 1.0)
```

### Watch mode

```bash
$ git graph-branch --watch
```

The graph takes over the terminal and updates whenever your branches or commits change. It opens on your current branch, and follows it when you check out another branch. Press `q` or Ctrl-C to quit.

To see the rest of a long graph, scroll with the mouse wheel, the Up/Down arrow keys, Page Up/Page Down, or Home/End. If you scroll your current branch out of view, the graph stays where you left it. Once your branch is back in view, the graph follows it again.

A plain drag does not select text in watch mode. In most terminals, hold Shift while you drag. In iTerm2, hold Option instead.

### PR status

If a branch's remote branch has an open pull request on GitHub, an icon shows the status of its reviews. A review does not count if it was dismissed, or if its reviewer was asked to review again (except for 🚧). Only the first icon in this list that matches shows:

- 👍 if the pull request has the approvals that the branch rules need, and no approver was asked to review again. If the repository has no review rules, one approval and no change requests is enough.
- 👎 if a reviewer requested changes.
- 🚧 if GitHub still shows changes requested, but each reviewer who requested changes was asked to review again, and for each of them, a different reviewer approved after that. GitHub blocks the merge until the old reviews are dismissed.
- 💬 if a review that only left comments (no approval or change request) has a thread that is not resolved. The thread stops counting if that reviewer later approves, or later has a review dismissed.
- 📭 if nothing above matches.

The review icon replaces 🔷 (in sync with the remote branch), because the pull request shows that the branch is pushed. 🔶 (out of sync) still shows, before the review icon.

After the review icon, a second icon shows the status of the pull request's checks: ❌ if any check failed, ⌛ if none failed and some are pending, and ✅ if all passed.

If the latest load of the checks or the reviews failed, or GitHub reports a check state that git-graph-branch does not know, one ⚠️ shows after the icons. The other icons keep the last status that loaded. If nothing has loaded yet, only ⚠️ shows.

This needs a token in an environment variable named after the first part of the GitHub domain: `GITHUB_TOKEN` for github.com, or `EXAMPLE_TOKEN` for example.com. git-graph-branch uses the `http.proxy` and `http.sslcainfo` settings from your git config.

In watch mode, the graph shows before the status loads. Until then, 🔌 shows on each branch that has a GitHub remote. When the status loads, the check icon replaces 🔌, or nothing does if the branch has no open pull request. If the load fails, ⚠️ replaces 🔌. While the review status loads, no review icon shows, so 🔷 shows if the branch is in sync. Without `--watch`, git-graph-branch waits for the status before it shows the graph.

In watch mode, the check status is checked every few seconds just after you push, and less often after that. The review status is checked every 5 minutes. In tmux, git-graph-branch does not check while its window is not visible. While it runs, it keeps a tmux session named `_git-graph-branch-<pid>`.

### Sample output

![Example repository Screenshot](docs/repo-screenshot.png)

Related branches are connected via lines; upstream branches are displayed further down the page. This allows rapidly grasping the structure of the branches.

To condense the information, the output is optimized for fonts like Hack or Cascadia Mono which correctly render box-drawing characters. It may display less well with other fonts.

![Key](docs/key.png)

### Recommended git configuration

git-graph-branch relies on your branches having upstream information set, which is not the case with git's defaults. To get the best out of git-graph-branch, I recommend a few configuration changes to your git checkout (`/path/to/repo/.git/config`, or `~/.gitconfig` if you would like to make these changes to every checkout):

```text
# Set upstream information when you run git checkout -b <branch>
[branch]
    autosetupmerge = always

# Ensure a plain git push will continue to work as expected
[push]
    default = simple
[remote]
    pushdefault = origin

# Keep branch history for longer
[gc]
    auto = 100000
```

If you have not used these defaults before, you may need to set up upstream information for your existing branches as a one-off. For instance, if `feature/foo` is going to be applied to `main`, run `git branch feature/foo --set-upstream-to=main`. Once you have made the config changes above, `git checkout main -b feature/foo` will set this upstream information for you automatically.
