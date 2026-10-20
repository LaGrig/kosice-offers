#!/bin/bash
cd ~/kosice-offers
git pull --rebase --autostash -q || true
.venv/bin/python scripts/$1.py "${@:2}"
git add docs
git commit -qm "update $1 $(date +%F_%H:%M)" || true
git push -q || true
