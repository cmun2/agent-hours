# Skins

A skin is one JSON file. It decides everything about how a run looks: colours, what each lane is
called, the icon for every event type, the layout, and how long a tool may go unanswered before the
view says so.

Drop a file in this directory and it shows up in the picker. Drag one onto the page to try it
without saving anything.

## The file

```json
{
  "name": "midnight",
  "author": "your-handle",
  "blurb": "One line. It shows under the timeline.",

  "colors": {
    "bg": "#0d1117", "panel": "#161b22", "line": "#21262d",
    "fg": "#e6edf3", "dim": "#8b949e", "accent": "#58a6ff"
  },

  "lanes": {
    "user":  { "color": "#a5d6ff", "label": "you" },
    "model": { "color": "#d2a8ff", "label": "model" },
    "tool":  { "color": "#7ee787", "label": "tool" },
    "conn":  { "color": "#8b949e", "label": "conn" },
    "run":   { "color": "#8b949e", "label": "run" }
  },

  "types": {
    "tool.error": { "color": "#ff7b72", "icon": "!" },
    "tool.call":  { "icon": "*" }
  },

  "layout": "timeline",
  "font": "mono",
  "radius": 11,
  "showMeta": true,
  "mergeDeltas": true,
  "glow": false,
  "stuckAfterMs": 5000
}
```

Only `name` and `colors` are required. Anything missing falls back: an unknown lane is drawn in
`dim` with its own name, an event type with no entry gets a dot.

| key | what it does |
|---|---|
| `layout` | `timeline` — dense rows. `cards` — each event boxed. `compact` — rows with no breathing room. |
| `font` | `mono` or `sans`. |
| `radius` | Corner radius in pixels, for the panels. |
| `showMeta` | Whether an event's `meta` is printed after its label. Off makes a much quieter view. |
| `mergeDeltas` | Fold consecutive `text.delta` events into one growing line. A run with forty of them is unreadable without this. |
| `glow` | Only in `cards`: the live event gets a halo. |
| `stuckAfterMs` | How long a tool call may go unanswered before the view calls it out. Lower is louder. |

## Event types worth styling

`user.message` · `model.started` · `model.completed` · `text.delta` · `tool.call` · `tool.result` ·
`tool.error` · `handoff` · `approval.requested` · `approval.granted` · `abort.requested` ·
`conn.lost` · `conn.retry` · `run.completed` · `run.failed`

A trace can carry any type it likes; these are the ones the shipped traces use.

## Submitting one

Open a pull request adding your file here. Keep it to one skin per file, give it an `author` and a
`blurb`, and check it against `gallery.html` first — every skin in this directory renders there, so
if it looks wrong in the gallery it will look wrong for everyone.

There is no taste requirement. A skin that is legible on a projector, or one that is all one colour,
or one that hides everything except tool calls, are all reasonable things to want.
