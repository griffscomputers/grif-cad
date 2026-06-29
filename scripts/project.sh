#!/usr/bin/env bash
# project.sh — manage per-part project folders + the projects/index.tsv catalog.
#
# Every built thing lives in its own folder projects/<slug>/ holding ALL of its files
# (source, renders, stl, step, gcode, csv, notes). Those folders are gitignored; only
# the catalog (projects/index.tsv) is tracked, so you can always "go back to the shed".
#
# Usage:
#   scripts/project.sh new <slug> [--engine openscad|cadquery] [--title "..."] [--tag a,b]
#   scripts/project.sh ls                 list the catalog
#   scripts/project.sh show <slug>        the row + every file in the folder ("go back to the shed")
#   scripts/project.sh render <slug>      render the source into its own folder
#   scripts/project.sh reindex            heal the catalog from disk (file counts, timestamps, new folders)
#   scripts/project.sh path <slug>        print the folder's absolute path
#   scripts/project.sh rm <slug> --yes    delete the folder + its catalog row
set -uo pipefail

proj="$(cd "$(dirname "$0")/.." && pwd)"
cd "$proj"
INDEX="projects/index.tsv"
HEADER=$'slug\tcreated\tupdated\tengine\ttitle\tstatus\tfiles\ttags\tnote'

mkdir -p projects
[ -f "$INDEX" ] || printf '%s\n' "$HEADER" > "$INDEX"

# ---- helpers ----------------------------------------------------------------
now()         { date -u +%FT%TZ; }
valid_slug()  { printf '%s' "${1:-}" | grep -qE '^[a-z0-9][a-z0-9_-]*$'; }
has_row()     { awk -F'\t' -v s="$1" 'NR>1 && $1==s{f=1} END{exit f?0:1}' "$INDEX"; }
count_files() { find "$1" -type f 2>/dev/null | wc -l | tr -d ' '; }

infer_engine() {  # by the files present in a folder
  local d="$1"
  if   ls "$d"/*.scad >/dev/null 2>&1; then echo openscad
  elif ls "$d"/*.py   >/dev/null 2>&1; then echo cadquery
  elif ls "$d"/*.ply  >/dev/null 2>&1; then echo scan
  else echo downloaded; fi
}

scaffold_scad() {  # $1 file  $2 slug  $3 title
  cat > "$1" <<EOF
// $3  ($2)
// units: millimeters. Edit the params, then:  scripts/project.sh render $2
\$fn = 64;

width  = 30;   // X
depth  = 30;   // Y
height = 20;   // Z

cube([width, depth, height], center = false);
EOF
}

scaffold_py() {  # $1 file  $2 slug  $3 title
  cat > "$1" <<EOF
"""$3 ($2) — CadQuery production model.
Run:  .venv/bin/python projects/$2/$2.py   ->  exports stl + step beside this file.
"""
import cadquery as cq

width, depth, height = 30.0, 30.0, 20.0  # mm

part = cq.Workplane("XY").box(width, depth, height)

cq.exporters.export(part, "projects/$2/$2.stl")
cq.exporters.export(part, "projects/$2/$2.step")
EOF
}

# ---- commands ---------------------------------------------------------------
cmd_new() {
  local slug="${1:-}"; shift || true
  local engine=openscad title="" tags=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --engine) engine="${2:-}"; shift 2 ;;
      --title)  title="${2:-}";  shift 2 ;;
      --tag|--tags) tags="${2:-}"; shift 2 ;;
      *) echo "new: unknown arg '$1'" >&2; return 2 ;;
    esac
  done
  valid_slug "$slug" || { echo "new: invalid slug '$slug' (use [a-z0-9][a-z0-9_-]*)" >&2; return 2; }
  case "$engine" in openscad|cadquery) ;; *) echo "new: --engine must be openscad|cadquery" >&2; return 2 ;; esac
  local dir="projects/$slug"
  [ -e "$dir" ]    && { echo "new: $dir already exists" >&2; return 1; }
  has_row "$slug"  && { echo "new: '$slug' already in catalog (try: scripts/project.sh reindex)" >&2; return 1; }

  mkdir -p "$dir"
  [ -n "$title" ] || title="$slug"
  local ext=scad
  if [ "$engine" = openscad ]; then scaffold_scad "$dir/$slug.scad" "$slug" "$title"
  else scaffold_py "$dir/$slug.py" "$slug" "$title"; ext=py; fi

  local ts; ts="$(now)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$slug" "$ts" "$ts" "$engine" "$title" "spec" "$(count_files "$dir")" "$tags" "" >> "$INDEX"

  echo "created $dir ($engine) — registered in $INDEX"
  echo "  edit:   $dir/$slug.$ext"
  echo "  render: scripts/project.sh render $slug"
}

cmd_ls() {
  local rows; rows="$(awk 'NR>1 && NF' "$INDEX" | wc -l | tr -d ' ')"
  [ "$rows" = 0 ] && { echo "no projects yet — scripts/project.sh new <slug>"; return 0; }
  column -t -s "$(printf '\t')" "$INDEX"
}

cmd_show() {
  local slug="${1:-}"
  valid_slug "$slug" || { echo "show: invalid slug" >&2; return 2; }
  local dir="projects/$slug"
  echo "== $slug =="
  if has_row "$slug"; then
    awk -F'\t' -v s="$slug" '
      NR==1 { for (i=1;i<=NF;i++) h[i]=$i; next }
      $1==s { for (i=1;i<=NF;i++) if ($i!="") printf "  %-9s %s\n", h[i]":", $i }
    ' "$INDEX"
  else
    echo "  (not in catalog — run: scripts/project.sh reindex)"
  fi
  echo "  ---- files ----"
  if [ -d "$dir" ]; then
    if [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then ( cd "$dir" && ls -lh | sed '1d;s/^/  /' )
    else echo "  (empty)"; fi
  else
    echo "  (no folder projects/$slug)"
  fi
}

cmd_render() {
  local slug="${1:-}"
  valid_slug "$slug" || { echo "render: invalid slug" >&2; return 2; }
  local dir="projects/$slug"
  [ -d "$dir" ] || { echo "render: no $dir (try: scripts/project.sh new $slug)" >&2; return 1; }
  local src=""
  if   [ -f "$dir/$slug.scad" ]; then src="$dir/$slug.scad"
  elif [ -f "$dir/$slug.stl"  ]; then src="$dir/$slug.stl"
  elif [ -f "$dir/$slug.py"   ]; then
    echo "render: $slug is CadQuery — export first:  .venv/bin/python $dir/$slug.py  (writes $slug.stl), then re-run" >&2
    return 1
  fi
  [ -n "$src" ] || { echo "render: no source in $dir ($slug.scad or $slug.stl)" >&2; return 1; }
  bash scripts/render.sh "$src" "$dir"
}

cmd_reindex() {
  # Gather filesystem facts per folder (no bash assoc arrays — macOS ships bash 3.2).
  local facts tmp sorted d s files mtime updated eng
  facts="$(mktemp)"; tmp="$(mktemp)"; sorted="$(mktemp)"
  for d in projects/*/; do
    [ -d "$d" ] || continue
    s="$(basename "$d")"
    files="$(count_files "$d")"
    mtime="$(find "$d" -type f -exec stat -f '%m' {} \; 2>/dev/null | sort -n | tail -1)"
    if [ -n "$mtime" ]; then updated="$(date -u -r "$mtime" +%FT%TZ)"; else updated="$(now)"; fi
    eng="$(infer_engine "$d")"
    printf '%s\t%s\t%s\t%s\n' "$s" "$files" "$updated" "$eng" >> "$facts"
  done

  # Merge in awk: existing catalog rows keep their metadata; folder facts refresh
  # files/updated; new folders are added; rows whose folder vanished are kept + warned.
  awk -F'\t' -v OFS='\t' -v FACTS="$facts" '
    FILENAME==FACTS { ff[$1]=$2; fu[$1]=$3; fe[$1]=$4; have[$1]=1; next }
    FNR==1 { print; next }                       # carry the header through
    $1=="" { next }
    { idx[$1]=1; cr[$1]=$2; en[$1]=$4; ti[$1]=$5; st[$1]=$6; tg[$1]=$8; no[$1]=$9 }
    END {
      for (k in have) all[k]=1
      for (k in idx)  all[k]=1
      for (k in all) {
        if (k in have) {
          c  = (k in cr && cr[k]!="") ? cr[k] : fu[k]
          e  = (k in en && en[k]!="") ? en[k] : fe[k]
          t2 = (k in ti && ti[k]!="") ? ti[k] : k
          s2 = (k in st && st[k]!="") ? st[k] : "spec"
          print k, c, fu[k], e, t2, s2, ff[k], (k in tg?tg[k]:""), (k in no?no[k]:"")
        } else {
          print "warn: " k " is in the catalog but its folder projects/" k " is missing (row kept)" > "/dev/stderr"
          print k, cr[k], cr[k], en[k], ti[k], st[k], "0", tg[k], no[k]
        }
      }
    }
  ' "$facts" "$INDEX" > "$tmp"

  # header first, body sorted by slug
  { head -n 1 "$tmp"; tail -n +2 "$tmp" | LC_ALL=C sort; } > "$sorted"
  mv "$sorted" "$INDEX"
  rm -f "$facts" "$tmp"
  echo "reindexed $INDEX"
}

cmd_path() {
  local slug="${1:-}"
  valid_slug "$slug" || { echo "path: invalid slug" >&2; return 2; }
  echo "$proj/projects/$slug"
}

cmd_rm() {
  local slug="${1:-}" yes="${2:-}"
  valid_slug "$slug" || { echo "rm: invalid slug" >&2; return 2; }
  if [ "$yes" != "--yes" ]; then
    echo "rm: deletes projects/$slug and its catalog row. Confirm with:" >&2
    echo "  scripts/project.sh rm $slug --yes" >&2
    return 1
  fi
  rm -rf "projects/$slug"
  local tmp; tmp="$(mktemp)"
  awk -F'\t' -v s="$slug" 'NR==1 || $1!=s' "$INDEX" > "$tmp" && mv "$tmp" "$INDEX"
  echo "removed projects/$slug + catalog row"
}

usage(){ sed -n '2,20p' "$0"; }

case "${1:-}" in
  new)     shift; cmd_new "$@" ;;
  ls)      cmd_ls ;;
  show)    shift; cmd_show "${1:-}" ;;
  render)  shift; cmd_render "${1:-}" ;;
  reindex) cmd_reindex ;;
  path)    shift; cmd_path "${1:-}" ;;
  rm)      shift; cmd_rm "${1:-}" "${2:-}" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; echo; usage; exit 2 ;;
esac
