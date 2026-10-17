# Security

Report vulnerabilities privately through [GitHub security advisories](https://github.com/halixm-dev/hok-ace-patch/security/advisories/new).
Do not attach game APKs, recovery material, account credentials or unredacted device logs to public issues.

## Signing keys

| Key | Purpose and limits |
|---|---|
| `resources/key/` | Intentionally shipped stable game re-signing key. It is public and cannot establish publisher identity. Never replace it during routine builds. |
| `android/signing/debug.keystore` | Previous patcher key, intentionally reused for debug and CI release APKs so existing installations can update in place. This key is public; anyone can sign with it. Obtain APKs only from trusted download locations. |
| CI release signing secrets | Configured with that same previous patcher key. Secret storage does not make an already-public key private. |

CI releases now use the previous patcher key and can update matching development installs without
uninstalling, preserving their private data. Android still requires compatible package/version
metadata. Signing compatibility does not remove installer prompts, Shizuku authorization, or
the patcher's explicit first-setup/data-loss consent. Normal/access game APKs continue to use
the separate unchanged key in `resources/key/`.

The previous patcher certificate's SHA-256 fingerprint is
`aa67f1993e3a335ff798d085a3e818b12988739dd3d5e69f8bdd1be97f01c249`.
Earlier private-signer releases used `91e25271c73e5dc7c241f9c0b7c4b8743e25bc54eb6d6e609f0cd58f0e42349c`.
An installation using that different signer cannot update directly to the previous key. Finish
pending recovery and export needed diagnostics before any uninstall; uninstalling removes
private recovery files. Existing published APKs do not change when CI secrets change.

Release CI requires `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_STORE_PASSWORD`,
`ANDROID_RELEASE_KEY_ALIAS` and `ANDROID_RELEASE_KEY_PASSWORD`. Back up the original keystore
and password securely; GitHub cannot return a stored secret. Local release builds remain unsigned
unless signing environment variables are supplied. CI supplies the previous patcher key explicitly.

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
