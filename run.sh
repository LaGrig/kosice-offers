#!/bin/bash
cd /home/ubuntu/kosice-offers
.venv/bin/python scripts/$1.py "${@:2}"
(
  flock 9
  git add docs
  git commit -qm "update $1 $(date +%F_%H:%M)" || true
  for i in 1 2 3; do
    git pull --rebase --autostash -q 2>/dev/null || git rebase --abort 2>/dev/null
    git push -q && break
    echo "git push не удался, попытка $i, жду" >&2
    sleep $((i * 20))
  done
) 9>/tmp/kosice-git.lock
