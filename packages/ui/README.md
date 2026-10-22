# @vns/ui

Shared React components used by both the web app and the desktop shell.

| Export | Purpose |
| --- | --- |
| `Modal` | Modal shell with overlay, header and footer slots |
| `Toasts` | Toast container (prop-driven, no store dependency) |
| `fmtTime`, `fmtBytes`, `fmtDuration`, `estimateSpeechSeconds` | Shared formatters |

Styles live in `apps/web/src/styles.css` and are shared by every surface that embeds
the UI.

## Licence

Apache-2.0, same as the parent repository.
