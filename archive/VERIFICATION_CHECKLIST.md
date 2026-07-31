# VERIFICATION_CHECKLIST

## Quality Gates for UI/UX
- [ ] No overlapping text or squished columns in Treeviews.
- [ ] CustomTkinter elements use designated Theme Colors (`#1E1E1E` background).
- [ ] Responsive resize: Grids (`grid_rowconfigure`, `grid_columnconfigure`) must be used for fluid layout.
- [ ] Scrollable views adapt correctly to long lists (e.g. patients, products).

## Quality Gates for Code
- [ ] No `// TODO` or `pass` placeholders left behind.
- [ ] Logs do not block the main thread.
- [ ] The `Simplicity First` principle is applied (no speculative programming).
- [ ] Ensure backward compatibility with existing databases.

## Security & Reliability
- [ ] Developer mode is authenticated only via secure `.pharmacy_dev.key` or Env Var.
- [ ] `DEV-PASS` plain-text backdoor is completely removed.
- [ ] External API network errors are gracefully handled or fail-fast logged.
