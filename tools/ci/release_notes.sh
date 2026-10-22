#!/usr/bin/env bash
# Print the player-facing release notes a new Android draft release starts from.
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

## Good to know

-

## Install

ARM64 Android 11 or newer, with Shizuku running. Install over ${version:-the previous version}; your translation and saved files are kept. Download the APK only from this repository, and check it against \`SHA256SUMS\`.
EOF
