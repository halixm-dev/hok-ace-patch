# Security

Report vulnerabilities privately through [GitHub security advisories](https://github.com/halixm-dev/hok-ace-patch/security/advisories/new).
Do not attach game APKs, recovery material, account credentials or unredacted device logs to public issues.

## Signing keys

| Key | Purpose and limits |
|---|---|
| `resources/key/` | Intentionally shipped stable game re-signing key. It is public and cannot establish publisher identity. Never replace it during routine builds. |
| `android/signing/debug.keystore` | Public development key, used only for debug APKs. Anyone can sign an APK with it; use trusted download locations. |
| Private Android release keystore | Separate patcher publisher identity. Stored in GitHub Actions secrets; never bundled in the APK or committed. |

A privately signed release cannot update an existing debug-signed patcher installation.
Finish any pending game recovery and export needed diagnostics before uninstalling the development
patcher. Uninstalling deletes its private recovery files. Then install the release APK and authorize Shizuku again.
Subsequent private releases use the same release key and can update in place.

The private release certificate's SHA-256 fingerprint is
`91e25271c73e5dc7c241f9c0b7c4b8743e25bc54eb6d6e609f0cd58f0e42349c`.

Release CI requires `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_STORE_PASSWORD`,
`ANDROID_RELEASE_KEY_ALIAS` and `ANDROID_RELEASE_KEY_PASSWORD`. Back up the original keystore
and password securely; GitHub cannot return a stored secret. Unsigned local release builds never
fall back to the public development key.

## Automation

Build jobs have read-only repository access; only the separate draft-release job can write releases.
Pull requests never receive release signing credentials. Actions are pinned to commit hashes,
downloads of Gradle, Gitleaks and native sources are checksum checked, and checkout credentials
are not retained. These controls follow [GitHub's Actions security guidance](https://docs.github.com/en/actions/reference/security/secure-use).
Dependabot checks action updates weekly. Gitleaks scans full history on pushes and pull requests.
The one scanner exception matches only historical prose about adopting verified recovery material.

The pre-publication scan found no detected credentials across 107 commits after reviewing two
false positives. The wrapper JAR matches Gradle's published checksum. The Android manifest and
exported worker/recovery providers were inspected for access restrictions. This is a targeted
review, not a complete audit of the app, compiled runtime, dependencies or bundled native binaries.
Release redistribution and broader device acceptance remain open in
[`android/native/THIRD_PARTY.md`](android/native/THIRD_PARTY.md); automated releases stay drafts.
