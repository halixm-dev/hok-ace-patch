#!/usr/bin/env bash
# Print the player-facing notes for a new Android and Windows draft release.
#
# Usage: tools/ci/release_notes.sh android-v1.7.1.2
#
# "What's new" is seeded with the feat: and fix: subjects since the previous android-v tag, which the
# maintainer rewrites for players before publishing (PRODUCT.md, Voice). The HTML comments do not render.
set -euo pipefail

tag="$1"
previous=$(git describe --tags --abbrev=0 --match 'android-v*' "${tag}^" 2>/dev/null || true)
range="${previous:+$previous..}$tag"
changes=$(git log --no-merges --format='%s' "$range" \
    | sed -nE 's/^(feat|fix)(\([^)]*\))?!?: (.*)$/- \u\3/p')
if [ -z "$changes" ]; then
    changes="- No changes players will notice."
fi
version="${previous#android-v}"

cat <<EOF
<!--
Before publishing:
- Rewrite each line under What's new for players: what changed, and what they now see or do.
  Drop lines players will not notice.
- Review android/native/THIRD_PARTY.md.
-->

## What's new

${changes}

## Install

### Android

Install \`hok-ace-patch.apk\` on an ARM64 device running Android 11 or newer, with Wireless debugging, Shizuku, or root. Install over ${version:-the previous version} to keep your translation and saved files.

### Windows

Run \`hok-ace-patch-windows-x64.exe\`. For the PC game, finish the game update, close the game and launcher, then select **PC** and your language. Select **Android USB** to patch a connected phone.

Check your download against \`SHA256SUMS\`.
EOF
