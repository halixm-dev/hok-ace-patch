# Security

Report vulnerabilities privately through [GitHub security advisories](https://github.com/halixm-dev/hok-ace-patch/security/advisories/new).
Do not attach game APKs, recovery material, account credentials or unredacted device logs to public issues.

## Signing keys

| Key | Purpose and limits |
|---|---|
| `resources/key/` | Intentionally shipped stable game re-signing key. It is public and cannot establish publisher identity. Never replace it during routine builds. |
| Current patcher key | Private. Held only by the maintainer and in the CI release secrets; never committed. Signs every release APK after 1.6.1.4, through APK Signature Scheme v3. |
| `android/signing/patcher.lineage` | Proof of rotation from the previous patcher key to the current one. Holds certificates only, no private key, so it is committed. |
| Previous patcher key | Public: it was committed to this repository's history, and anyone can sign with it. Kept in the lineage only so installs signed with it update in place. |

Release APKs are signed v3-only (minSdk is 30) with the current key and the lineage. An install
signed with the previous key accepts the update and keeps its private data. Once a phone has
installed a rotated release, Android refuses any later APK signed only with the previous key (the
lineage withholds its rollback capability), so the public key can no longer take over that install.
A phone that never updates stays exposed: anyone can still offer it an update signed with the
previous key. Rotation does not remove installer prompts, Shizuku authorization, or the patcher's
explicit first-setup/data-loss consent. Normal/access game APKs keep the separate key in `resources/key/`.

| Certificate | SHA-256 |
|---|---|
| Current patcher key | `555f2ff48b44a98395f6c305df13f74122545ab4eb57bb8f8d4267bf300b8ae5` |
| Previous patcher key (1.6.1.4 and earlier) | `aa67f1993e3a335ff798d085a3e818b12988739dd3d5e69f8bdd1be97f01c249` |
| Earlier private signer | `91e25271c73e5dc7c241f9c0b7c4b8743e25bc54eb6d6e609f0cd58f0e42349c` |

An installation using the earlier private signer is not in the lineage and cannot update directly.
Finish pending recovery and export needed diagnostics before any uninstall; uninstalling removes
private recovery files. Existing published APKs do not change when CI secrets change.

Release CI requires `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_STORE_PASSWORD`,
`ANDROID_RELEASE_KEY_ALIAS` and `ANDROID_RELEASE_KEY_PASSWORD`, holding the current key. Back up
the keystore and its password securely; GitHub cannot return a stored secret, and losing the key
ends in-place updates. `tools/ci/sign_android.ps1` applies the lineage after the Gradle build.
Locally, set `ANDROID_RELEASE_KEYSTORE` to the keystore path plus the same three password and alias
variables; Gradle then signs debug and release builds with the current key but without the lineage,
so run `tools/ci/sign_android.ps1 -Apk <apk>` before installing over a phone still on the previous
key. Without the variables, debug builds use the PC's SDK debug key and release builds stay
unsigned. Push and pull-request APKs in CI are signed with the runner's throwaway key.

## Automation

Build jobs have read-only repository access; only the separate draft-release job can write releases.
Pull requests never receive release signing credentials. Actions are pinned to commit hashes,
downloads of Gradle, Gitleaks and native sources are checksum checked, and checkout credentials
are not retained. These controls follow [GitHub's Actions security guidance](https://docs.github.com/en/actions/reference/security/secure-use).
Dependabot checks action updates weekly. Gitleaks scans full history on pushes and pull requests.
The one scanner exception matches only historical prose about adopting verified recovery material.

The pre-publication history and committed-source scans found no detected credentials after
reviewing the documented false positives. See the [lab notebook evidence](docs/lab-notebook.md#2026-10-17--public-repository-and-android-release-automation).
The wrapper JAR matches Gradle's published checksum. The Android manifest and
exported worker/recovery providers were inspected for access restrictions. This is a targeted
review, not a complete audit of the app, compiled runtime, dependencies or bundled native binaries.
Release redistribution and broader device acceptance remain open in
[`android/native/THIRD_PARTY.md`](android/native/THIRD_PARTY.md); automated releases stay drafts.
