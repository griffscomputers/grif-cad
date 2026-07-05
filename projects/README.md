# projects/ — one folder per part

Every thing you build gets its **own folder** here, holding *all* of its files — source,
renders, mesh, G-code, data, notes. Those folders are **not checked into git** (so the repo
stays the harness, not a junk drawer of parts). The repo tracks only:

- **`index.tsv`** — the catalog (one row per part). This is how you "go back to the shed."
- **`README.md`** — this file.

Everything else under `projects/` is gitignored (see the `/projects/*` rules in `.gitignore`).

## Layout

```
projects/
  index.tsv                # tracked catalog
  README.md                # tracked
  <slug>/                  # gitignored — the whole life of one part
    <slug>.scad | <slug>.py        # source (OpenSCAD or CadQuery)
    <slug>-iso.png  -front  -side  -top   # renders
    <slug>.stl  <slug>.step  <slug>.gcode  # mesh / archive / sliced
    *.csv  notes.md                 # any data or notes
```

The folder name is the **slug**, and files are named by it — the slug *is* the part's identity.

## Catalog columns (`index.tsv`, tab-separated)

`slug  created  updated  engine  title  status  files  tags  note`

- **engine**: `openscad` · `cadquery` · `scan` · `downloaded`
- **status**: `spec` · `proto` · `prod` · `sliced` · `printed`
- **files**: count on disk (kept fresh by `reindex`)

## Use it — `scripts/project.sh`

```bash
scripts/project.sh new shed --title "Garden shed 12x20"   # make + register a new part
scripts/project.sh ls                                     # list the catalog
scripts/project.sh show shed                              # "go back to the shed" — row + all its files
scripts/project.sh render shed                            # render the source into its own folder
scripts/project.sh reindex                                # heal the catalog from disk
scripts/project.sh path shed                              # print the folder path
```

> The web chat bridge renders straight into `projects/<slug>/` too, so chat-built and
> CLI-built parts live the same way.
