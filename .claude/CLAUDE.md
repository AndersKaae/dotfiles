# Global instructions

These apply across all projects, in addition to any project-specific CLAUDE.md.

## Clean up after yourself

When a task created a scratch database, Docker volume, large temp file/directory, or other sizable disposable artifact, don't just leave it. Before ending the session (or when a natural checkpoint is reached), explicitly ask "can this be deleted now?" and act on the answer.

- If the artifact is clearly no longer needed, delete it — but treat deletion as a destructive action: confirm with the user first unless they've already told you to clean up proactively.
- If it might still be needed (e.g. tied to ongoing investigation or a plan doc still open), say so explicitly rather than silently leaving it — flag it as "kept because X" so it doesn't get forgotten as dead weight.
- This applies to things like: one-off/scratch databases, Docker volumes, large exported files, ad-hoc investigation notes/docs, and generated output directories (test runs, profiling results, etc.) that were only needed for the task at hand.
