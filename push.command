#!/bin/bash
cd "$(dirname "$0")" || exit 1
rm -rf __pycache__ 2>/dev/null
[ -d .git ] || git init -q
git add -A
echo "== Files being committed (.env must NOT be listed):"
git status --short
if git status --short | grep -q "\.env$"; then echo "STOP: .env is staged. Aborting."; exit 1; fi
git commit -qm "LocalBridge: two-way Indian-language voice translator (Sarvam AI)" || true
git branch -M main
if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  gh repo create localbridge-sarvam --public --source=. --remote=origin --push
else
  read -r -p "Paste your empty GitHub repo URL (https://github.com/you/repo.git): " URL
  git remote remove origin 2>/dev/null; git remote add origin "$URL"
  git push -u origin main
fi
echo "== Done."
