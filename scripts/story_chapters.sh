#!/usr/bin/env bash
# Generate a serial story's chapters in order, one vgi job per chapter (subject ch01, ch02, …).
#
#   scripts/story_chapters.sh plan   [FROM] [TO]   Part A for each chapter: new job (or reuse) → script → keyframes → storyboard
#   scripts/story_chapters.sh render [FROM] [TO]   Part B for each chapter in order: render → qa → export (needs `vgi approve`)
#   scripts/story_chapters.sh auto   [FROM] [TO]   everything unattended, auto-approving each plan (no human review)
#   scripts/story_chapters.sh status [FROM] [TO]   chapter → job id → state
#
# FROM/TO are chapter numbers (default 1 and the story's last chapter). TOPIC selects the topic (default
# meerkat_story); every vgi option still applies through the environment (VGI_ENV=linux_4x4090, VGI_ROOT).
# DRY_RUN=1 pushes placeholder chapters through plan/auto with stub models, to check the plumbing.
# The newest job whose topic and subject match a chapter is reused, so a stopped run resumes where it left off;
# render/auto stop at the first chapter that is not ready, so the release order is never broken.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

TOPIC="${TOPIC:-meerkat_story}"
cmd="${1:-}"; shift || true

py() { uv run python - "$@"; }
DRY=(); [[ -n "${DRY_RUN:-}" ]] && DRY=(--dry-run)
dry() { echo ${DRY[@]+"${DRY[@]}"}; }

n_chapters=$(py "$TOPIC" <<'PY'
import sys
from vgi.cli import find_root
from vgi.config import load_yaml
root = find_root()
t = load_yaml(root / "configs" / "topics" / f"{sys.argv[1]}.yaml")
print(len(load_yaml(root / t["story_dir"] / "story.yaml")["chapters"]))
PY
)
FROM="${1:-1}"; TO="${2:-$n_chapters}"

# newest job for a chapter: prints "<job id> <state>" or nothing
job_for() {
  py "$TOPIC" "$1" <<'PY'
import sys
from vgi.cli import find_root, jobs_root
from vgi.core.job import Job
topic, subject = sys.argv[1], sys.argv[2]
hits = sorted(p.parent for p in jobs_root(find_root()).glob("*/manifest.json")
              if (m := Job(p.parent).manifest).topic == topic and m.subject == subject)
if hits:
    m = Job(hits[-1]).manifest
    print(m.job_id, m.state)
PY
}

ensure_job() {   # prints the chapter's job id, creating the job if none exists
  local subject="$1" found
  found=$(job_for "$subject")
  if [[ -z "$found" ]]; then
    uv run vgi new --topic "$TOPIC" --subject "$subject" >&2
    found=$(job_for "$subject")
  fi
  echo "${found%% *}"
}

case "$cmd" in
  plan)
    for ((n = FROM; n <= TO; n++)); do
      s=$(printf 'ch%02d' "$n"); id=$(ensure_job "$s")
      echo "== $s  $id: plan"
      uv run vgi plan "$id" $(dry)
    done
    echo "Review each storyboard (outputs/jobs/<id>/04_storyboard/preview.html), fix shots with"
    echo "\`uv run vgi pick <id> <beat.shot> <candidate>\`, then \`uv run vgi approve <id>\` and run: $0 render $FROM $TO"
    ;;
  render)
    for ((n = FROM; n <= TO; n++)); do
      s=$(printf 'ch%02d' "$n"); found=$(job_for "$s"); id="${found%% *}"; state="${found##* }"
      case "$state" in
        exported) echo "== $s  $id: already exported"; continue ;;
        approved|rendered|qa_failed|qa_passed) ;;
        "") echo "$s has no job; run: $0 plan $n" >&2; exit 1 ;;
        *) echo "$s ($id) is $state; review and \`uv run vgi approve $id\` first" >&2; exit 1 ;;
      esac
      echo "== $s  $id: render → qa → export"
      uv run vgi render "$id"
      uv run vgi qa "$id"
      [[ "$(job_for "$s")" == *qa_passed ]] || {
        echo "$s failed QA: outputs/jobs/$id/09_final/qa_report.md (fix, or \`uv run vgi qa $id --override --reason ...\`)" >&2; exit 1; }
      uv run vgi export "$id"
    done
    ;;
  auto)
    for ((n = FROM; n <= TO; n++)); do
      s=$(printf 'ch%02d' "$n"); id=$(ensure_job "$s")
      [[ "$(job_for "$s")" == *exported ]] && { echo "== $s  $id: already exported"; continue; }
      echo "== $s  $id: full run (auto-approved)"
      uv run vgi run "$id" --auto-approve $(dry) || true      # a QA failure makes export refuse; reported below
      [[ "$(job_for "$s")" == *exported ]] || {
        echo "$s stopped before export: \`uv run vgi logs $id\`, outputs/jobs/$id/09_final/qa_report.md" >&2; exit 1; }
    done
    ;;
  status)
    for ((n = FROM; n <= TO; n++)); do
      s=$(printf 'ch%02d' "$n"); found=$(job_for "$s")
      printf '%s  %s\n' "$s" "${found:-(no job)}"
    done
    ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
