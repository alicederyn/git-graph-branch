I want to be able to say "n commits unmerged" or "this branch has been merged to upstream" and have that take into account:

1) merge commits from branch to upstream
2) merge commits from upstream to branch
3) octopus merges
4) indirect merges via merged-in histories

(It would be *amazing* to also take into account squash commits, but that seems... Ambitious.)
