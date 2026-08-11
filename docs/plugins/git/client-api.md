# Git Client API

The Git plugin adds core Git operations to Titan through a high-level client and reusable workflows. It covers branches, commits, status inspection, diffs, remotes, stashes, tags, and worktrees.

This page documents the plugin from a functional point of view, while also showing how each capability is called and which parameters it needs.

---

## Requirements

To use the Git plugin in a project:

- Enable the `git` plugin in `.titan/config.toml`
- Install the `git` CLI and make sure it is available in `PATH`
- Run Titan inside a Git repository

Example project configuration:

```toml
[plugins.git]
enabled = true

[plugins.git.config]
main_branch = "main"
default_remote = "origin"
```

---

## Accessing the client

In Titan code, the public entry point is the Git plugin client:

```python
git_plugin = config.registry.get_plugin("git")
client = git_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

---

## Branch operations

### Get the current branch

Returns the currently checked out branch name.

**Call:**

```python
client.get_current_branch()
```

**Parameters:**

- No parameters.

### List branches

Returns local branches, or remote branches when requested.

**Call:**

```python
client.get_branches(remote=False)
```

**Parameters:**

- `remote`: Optional. Set to `True` to list remote branches instead of local ones.

### Create a branch

Creates a new branch from a starting point.

**Call:**

```python
client.create_branch(branch_name="feature/search", start_point="HEAD")
```

**Parameters:**

- `branch_name`: Required. New branch name.
- `start_point`: Optional. Git ref to branch from.

### Delete a branch

Deletes a branch directly.

**Call:**

```python
client.delete_branch(branch="feature/search", force=False)
```

**Parameters:**

- `branch`: Required. Branch name to delete.
- `force`: Optional. Force deletion.

### Delete a branch safely

Deletes a branch only if it is not considered protected.

**Call:**

```python
client.safe_delete_branch(branch="feature/search", force=False)
```

**Parameters:**

- `branch`: Required. Branch name to delete.
- `force`: Optional. Force deletion.

### Checkout a branch

Switches the repository to another branch.

**Call:**

```python
client.checkout("feature/search")
```

**Parameters:**

- `branch`: Required. Branch name to checkout.

### Check whether a branch exists on remote

Checks if a branch already exists in a remote repository.

**Call:**

```python
client.branch_exists_on_remote(branch="feature/search", remote="origin")
```

**Parameters:**

- `branch`: Required. Branch name.
- `remote`: Optional. Remote name.

### Update a branch from remote

Fetches and fast-forwards a branch from the remote.

**Call:**

```python
client.update_branch(branch="main", remote="origin")
```

**Parameters:**

- `branch`: Required. Branch to update.
- `remote`: Optional. Remote name. Defaults to the configured default remote.

### Update from the configured main branch

Updates the current branch from the configured main branch.

**Call:**

```python
client.update_from_main()
```

**Parameters:**

- No parameters.

### Checkout safely

Stores the current branch, optionally stashes local changes, and then switches branches.

**Call:**

```python
client.safe_checkout(branch="feature/search", auto_stash=True)
```

**Parameters:**

- `branch`: Required. Branch to checkout.
- `auto_stash`: Optional. Automatically stash uncommitted changes first.

### Return to the original branch

Returns to the branch previously saved by `safe_checkout`.

**Call:**

```python
client.return_to_original_branch()
```

**Parameters:**

- No parameters.

### Check whether a branch is protected

Checks if a branch name is treated as protected by the client.

**Call:**

```python
client.is_protected_branch("main")
```

**Parameters:**

- `branch`: Required. Branch name.

---

## Commit operations

### Create a commit

Creates a commit from the current working tree.

**Call:**

```python
client.commit(message="feat: add search filters", all=False, no_verify=True)
```

**Parameters:**

- `message`: Required. Commit message.
- `all`: Optional. Include tracked modified files automatically.
- `no_verify`: Optional. Skip Git hooks.

### Create a commit for specific files

Creates a commit only for the files passed in the call.

**Call:**

```python
client.commit_files(
    files=["src/search.py", "tests/test_search.py"],
    message="test: cover search filters",
    no_verify=True,
)
```

**Parameters:**

- `files`: Required. Files to include in the commit.
- `message`: Required. Commit message.
- `no_verify`: Optional. Skip Git hooks.

### Get the current commit SHA

Returns the SHA of `HEAD`.

**Call:**

```python
client.get_current_commit()
```

**Parameters:**

- No parameters.

### Get the commit SHA for a ref

Resolves any Git ref to its commit SHA.

**Call:**

```python
client.get_commit_sha("HEAD~1")
```

**Parameters:**

- `ref`: Required. Any Git ref.

### Get commits versus base

Returns commit messages from the base branch up to `HEAD`.

**Call:**

```python
client.get_commits_vs_base()
```

**Parameters:**

- No parameters.

### Get commits in a branch compared to another branch

Returns the commits present in the head branch but not in the base branch.

**Call:**

```python
client.get_branch_commits(base_branch="main", head_branch="feature/search")
```

**Parameters:**

- `base_branch`: Required. Base branch.
- `head_branch`: Required. Head branch.

### Get commits between refs

Returns commits reachable from one ref but not another.

**Call:**

```python
client.get_commits_between_refs(base_ref="origin/main", head_ref="HEAD")
```

**Parameters:**

- `base_ref`: Required. Base ref.
- `head_ref`: Optional. Head ref.

### Count commits ahead of a base branch

Counts how many commits the current branch is ahead of another branch.

**Call:**

```python
client.count_commits_ahead(base_branch="main")
```

**Parameters:**

- `base_branch`: Optional. Base branch to compare against.

### Count unpushed commits

Counts how many commits have not been pushed to the remote yet.

**Call:**

```python
client.count_unpushed_commits(branch=None, remote="origin")
```

**Parameters:**

- `branch`: Optional. Branch to inspect. Uses the current branch when omitted.
- `remote`: Optional. Remote name.

---

## Status operations

### Get repository status

Returns a structured view of the current repository state.

**Call:**

```python
client.get_status()
```

**Parameters:**

- No parameters.

### Check for uncommitted changes

Returns whether the repository has local changes not yet committed.

**Call:**

```python
client.has_uncommitted_changes()
```

**Parameters:**

- No parameters.

---

## Diff operations

### Get a diff between refs

Returns the diff between two refs.

**Call:**

```python
client.get_diff(base_ref="origin/main", head_ref="HEAD")
```

**Parameters:**

- `base_ref`: Required. Base ref.
- `head_ref`: Optional. Head ref.

### Get the full uncommitted diff

Returns the diff of all local changes.

**Call:**

```python
client.get_uncommitted_diff()
```

**Parameters:**

- No parameters.

### Get the staged diff

Returns only the staged changes.

**Call:**

```python
client.get_staged_diff()
```

**Parameters:**

- No parameters.

### Get the unstaged diff

Returns only the unstaged changes.

**Call:**

```python
client.get_unstaged_diff()
```

**Parameters:**

- No parameters.

### Get the diff for one file

Returns the diff for a single file path.

**Call:**

```python
client.get_file_diff("src/search.py")
```

**Parameters:**

- `file_path`: Required. File path to inspect.

### Get the diff between branches

Returns the diff between two branches, with configurable context lines.

**Call:**

```python
client.get_branch_diff(
    base_branch="main",
    head_branch="feature/search",
    context_lines=3,
    use_remote=False,
)
```

**Parameters:**

- `base_branch`: Required. Base branch.
- `head_branch`: Required. Head branch.
- `context_lines`: Optional. Number of diff context lines.
- `use_remote`: Optional. Treat both branches as remote refs.

### Get per-file change counters between branches

Returns a `UIFileChurn` list with exact additions/deletions per changed file
(`git diff --numstat`). Binary files are included with `is_binary=True` and zero
counters. Useful when an API source reports zeroed counters for files whose diff
it cannot render.

**Call:**

```python
client.get_branch_numstat(
    base_branch="main",
    head_branch="feature/search",
    use_remote=False,
)
```

**Parameters:**

- `base_branch`: Required. Base branch.
- `head_branch`: Required. Head branch.
- `use_remote`: Optional. Treat both branches as remote refs.

### Get a diff stat between refs

Returns a summary of file-level changes between refs.

**Call:**

```python
client.get_diff_stat(base_ref="origin/main", head_ref="HEAD")
```

**Parameters:**

- `base_ref`: Required. Base ref.
- `head_ref`: Optional. Head ref.

### Get the diff stat for uncommitted changes

Returns a compact summary of local changes.

**Call:**

```python
client.get_uncommitted_diff_stat()
```

**Parameters:**

- No parameters.

### Get the diff stat between branches

Returns a compact summary of changes between two branches.

**Call:**

```python
client.get_branch_diff_stat(base_branch="main", head_branch="feature/search")
```

**Parameters:**

- `base_branch`: Required. Base branch.
- `head_branch`: Required. Head branch.

---

## Merge operations

### Merge a ref into the current branch

Merges a ref into the checked out branch without opening an editor. A conflicted merge is **not** an error: the call returns `ClientSuccess` with a `UIMergeResult` whose `status` is `MergeStatus.CONFLICTED` and whose `conflicted_files` lists the unmerged paths, so the caller can drive conflict resolution.

**Call:**

```python
client.merge(ref="origin/develop", target_branch="feature/search", no_ff=False)
```

**Parameters:**

- `ref`: Required. Ref to merge, usually a remote-tracking ref such as `origin/develop`.
- `target_branch`: Optional. Branch receiving the merge. Used for display only.
- `no_ff`: Optional. Force a merge commit even when a fast-forward is possible.

**Returns:** `ClientResult[UIMergeResult]` with `status` in `up_to_date`, `fast_forward`, `merged`, `conflicted`.

### List conflicted files

Returns the paths git reports as unmerged in the index. Empty when the tree is clean.

Note that git keeps a path unmerged until it is staged, so a file whose conflict was already fixed in the editor still shows up here. Use *List unresolved conflicts* when you need to know whether the conflicts are actually gone.

**Call:**

```python
client.get_conflicted_files()
```

**Parameters:** none.

### List unresolved conflicts

Returns only the unmerged paths whose working-tree content still contains conflict markers (`<<<<<<<` … `>>>>>>>`). Files that were resolved but not staged are excluded; paths that cannot be read (deleted or binary) are kept in the list so the caller can decide.

**Call:**

```python
client.get_unresolved_conflict_files()
```

**Parameters:** none.

### Check whether a merge is in progress

Returns `True` while `MERGE_HEAD` exists, that is, while a merge is stopped and waiting to be completed or aborted.

**Call:**

```python
client.is_merge_in_progress()
```

**Parameters:** none.

### Stage every change

Stages the whole working tree, including untracked files. Used to mark conflicts as resolved before completing a merge.

**Call:**

```python
client.stage_all()
```

**Parameters:** none.

### Complete an in-progress merge

Commits the staged merge using the message git prepared, without opening an editor.

**Call:**

```python
client.continue_merge()
client.continue_merge(no_verify=False)
```

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `no_verify` | No | `True` | Skip pre-commit and commit-msg hooks. Skipping is the default because the commit only carries git's own merge message, and a hook that fails here leaves the merge stopped with everything staged. |

**Returns:** `ClientResult[str]` with the merge commit SHA.

### Abort an in-progress merge

Restores the state from before the merge started.

**Call:**

```python
client.abort_merge()
```

**Parameters:** none.

## Remote operations

### Push to a remote

Pushes commits to a remote branch.

**Call:**

```python
client.push(remote="origin", branch="feature/search", set_upstream=True, tags=False)
```

**Parameters:**

- `remote`: Optional. Remote name.
- `branch`: Optional. Branch to push. Uses the current branch when omitted.
- `set_upstream`: Optional. Set the upstream tracking branch.
- `tags`: Optional. Push tags too.

### Push a tag

Pushes a single tag to a remote.

**Call:**

```python
client.push_tag(tag_name="v1.2.0", remote="origin")
```

**Parameters:**

- `tag_name`: Required. Tag name.
- `remote`: Optional. Remote name.

### Pull from a remote

Pulls changes from a remote branch.

**Call:**

```python
client.pull(remote="origin", branch="main")
```

**Parameters:**

- `remote`: Optional. Remote name.
- `branch`: Optional. Branch to pull.

### Fetch from a remote

Fetches changes without merging them.

**Call:**

```python
client.fetch(remote="origin", branch="main", all=False)
```

**Parameters:**

- `remote`: Optional. Remote name.
- `branch`: Optional. Branch to fetch.
- `all`: Optional. Fetch all remotes.

### Extract GitHub repository info

Parses the remote URL and returns the GitHub owner and repository name when available.

**Call:**

```python
client.get_github_repo_info()
```

**Parameters:**

- No parameters.

---

## Stash operations

### Create a stash

Stashes current local changes.

**Call:**

```python
client.stash_push(message="temporary local changes")
```

**Parameters:**

- `message`: Optional. Stash message.

### Pop a stash

Applies and removes a stash.

**Call:**

```python
client.stash_pop(stash_ref=None)
```

**Parameters:**

- `stash_ref`: Optional. Specific stash reference.

### Find a stash by message

Looks up a stash using its message.

**Call:**

```python
client.find_stash_by_message("temporary local changes")
```

**Parameters:**

- `message`: Required. Stash message to search for.

### Restore a stash by message

Finds a stash by message and restores it.

**Call:**

```python
client.restore_stash("temporary local changes")
```

**Parameters:**

- `message`: Required. Stash message to restore.

---

## Tag operations

### Create a tag

Creates an annotated tag.

**Call:**

```python
client.create_tag(tag_name="v1.2.0", message="Release 1.2.0", ref="HEAD")
```

**Parameters:**

- `tag_name`: Required. Tag name.
- `message`: Required. Tag annotation message.
- `ref`: Optional. Ref to tag.

### Delete a tag

Deletes a local tag.

**Call:**

```python
client.delete_tag("v1.2.0")
```

**Parameters:**

- `tag_name`: Required. Tag name.

### Check whether a tag exists locally

Checks if a tag is present in the local repository.

**Call:**

```python
client.tag_exists("v1.2.0")
```

**Parameters:**

- `tag_name`: Required. Tag name.

### Check whether a tag exists on remote

Checks if a tag exists in a remote repository.

**Call:**

```python
client.remote_tag_exists(tag_name="v1.2.0", remote="origin")
```

**Parameters:**

- `tag_name`: Required. Tag name.
- `remote`: Optional. Remote name.

### List tags

Returns the tags available in the repository.

**Call:**

```python
client.list_tags()
```

**Parameters:**

- No parameters.

---

## Worktree operations

### Create a worktree

Creates a new Git worktree.

**Call:**

```python
client.create_worktree(
    path="../repo-search-worktree",
    branch="feature/search",
    create_branch=False,
    detached=False,
)
```

**Parameters:**

- `path`: Required. Filesystem path for the worktree.
- `branch`: Required. Branch to attach to the worktree.
- `create_branch`: Optional. Create the branch if needed.
- `detached`: Optional. Create the worktree in detached mode.

### Remove a worktree

Removes an existing worktree.

**Call:**

```python
client.remove_worktree(path="../repo-search-worktree", force=False)
```

**Parameters:**

- `path`: Required. Worktree path.
- `force`: Optional. Force removal.

### Prune stale worktree metadata

Clears Git's records for worktrees whose directories no longer exist.

Git keeps administrative data under `.git/worktrees` for every registered worktree. If
the directory is deleted by hand, or a removal is interrupted, that record survives and
blocks the path: `create_worktree` reports it as already registered, while
`remove_worktree` reports it as "not a working tree". Pruning is the only way to clear
it, so call this before recreating a worktree at a path a previous run may have used.

**Call:**

```python
client.prune_worktrees()
```

**Parameters:**

- No parameters.

### List worktrees

Returns all worktrees for the repository.

**Call:**

```python
client.list_worktrees()
```

**Parameters:**

- No parameters.

### Run a Git command in a worktree

Runs a Git command inside a specific worktree.

**Call:**

```python
client.run_in_worktree(worktree_path="../repo-search-worktree", args=["status", "--short"])
```

**Parameters:**

- `worktree_path`: Required. Worktree path.
- `args`: Required. Git arguments to execute.

### Get recent commits from a worktree

Returns recent commits from a specific worktree.

**Call:**

```python
client.get_commits(worktree_path="../repo-search-worktree", limit=10)
```

**Parameters:**

- `worktree_path`: Required. Worktree path.
- `limit`: Optional. Maximum number of commits.

### Get the worktree diff stat

Returns a diff summary for local changes in a worktree.

**Call:**

```python
client.get_worktree_diff_stat(worktree_path="../repo-search-worktree")
```

**Parameters:**

- `worktree_path`: Required. Worktree path.

### Checkout a branch in a worktree

Checks out, or creates, a branch inside a specific worktree.

**Call:**

```python
client.checkout_branch_in_worktree(
    worktree_path="../repo-search-worktree",
    branch_name="feature/search",
    force=False,
)
```

**Parameters:**

- `worktree_path`: Required. Worktree path.
- `branch_name`: Required. Branch name.
- `force`: Optional. Force the checkout.

### Commit changes in a worktree

Stages and commits changes inside a worktree.

**Call:**

```python
client.commit_in_worktree(
    worktree_path="../repo-search-worktree",
    message="feat: add search filters",
    add_all=True,
    no_verify=False,
)
```

**Parameters:**

- `worktree_path`: Required. Worktree path.
- `message`: Required. Commit message.
- `add_all`: Optional. Stage all tracked changes before committing.
- `no_verify`: Optional. Skip Git hooks.

### Push from a worktree

Pushes a branch from a specific worktree to a remote.

**Call:**

```python
client.push_from_worktree(
    worktree_path="../repo-search-worktree",
    branch="feature/search",
    remote="origin",
)
```

**Parameters:**

- `worktree_path`: Required. Worktree path.
- `branch`: Required. Branch to push.
- `remote`: Optional. Remote name.

---

## Related workflows

The Git plugin ships with workflows that use these capabilities directly:

- `commit-ai`: Checks repository status, shows a summary of local changes, generates a commit message with AI, creates the commit, and pushes it

These workflows can be used as-is or extended from `.titan/workflows/`.
