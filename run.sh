#!/bin/bash
cd /home/ubuntu/kosice-offers
.venv/bin/python scripts/$1.py "${@:2}"
(
  flock 9
  git add docs
  git commit -qm "update $1 $(date +%F_%H:%M)" || true
  git pull --rebase --autostash -q || git rebase --abort
  git push -q
) 9>/tmp/kosice-git.lock
