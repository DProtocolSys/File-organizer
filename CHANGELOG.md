# Changelog

## Unreleased

- New application icon (cards sorted into columns), generated from a single shared design.
- Recent folders can be cleared (*Clear*) or removed one by one (✕).

## 1.0.0

- New graphical interface: drag & drop, preview with per-file and per-category
  selection, search, progress, result summary, light/dark theme.
- Conflict handling: the user chooses *Keep both*, *Replace* or *Skip*, per file or
  for all remaining conflicts.
- Undo of the last run, with backups of replaced files.
- All-or-nothing execution with automatic rollback, and cancellation.
- Command-line interface (`file-organizer-cli`) with dry-run and conflict policies.
- Faster planning: one directory listing per destination, O(1) extension lookup,
  no per-file path resolution.
- More file types and categories (presentations, ebooks, fonts, …); optional
  `Other` folder for unrecognized files.
- Safety: symlinks and hidden files ignored, system folders refused.
- Case-insensitive collision detection on every operating system (fixes a test
  that only passed on Windows/macOS).
- Standalone executables built by GitHub Actions; tests run on Windows, macOS and Linux.
