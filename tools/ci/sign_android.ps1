# Re-sign a patcher APK with the current patcher key and the rotation lineage.
# The lineage proves the previous (public) patcher key handed over to the current one, so an
# install signed with the previous key updates in place. Reads the four ANDROID_RELEASE_* variables.
param(
    [Parameter(Mandatory)][string]$Apk,
    [string]$Lineage = 'android/signing/patcher.lineage'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

foreach ($name in 'ANDROID_RELEASE_KEYSTORE', 'ANDROID_RELEASE_STORE_PASSWORD', 'ANDROID_RELEASE_KEY_ALIAS', 'ANDROID_RELEASE_KEY_PASSWORD') {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "$name is required" }
}
$sdk = $env:ANDROID_HOME
if (-not $sdk) { throw 'ANDROID_HOME is required' }
$apksigner = "$sdk/build-tools/35.0.0/apksigner.bat"
$signed = "$Apk.signed"

# minSdk is 30, so v3 alone covers every supported device; v1/v2 would need the previous key.
# Rotation targets API 28 so the rotated key sits in the plain v3 block, not v3.1 (API 33+).
& $apksigner sign --ks $env:ANDROID_RELEASE_KEYSTORE --ks-key-alias $env:ANDROID_RELEASE_KEY_ALIAS `
    --ks-pass env:ANDROID_RELEASE_STORE_PASSWORD --key-pass env:ANDROID_RELEASE_KEY_PASSWORD `
    --lineage $Lineage --rotation-min-sdk-version 28 --alignment-preserved true `
    --v1-signing-enabled false --v2-signing-enabled false --v3-signing-enabled true --v4-signing-enabled false `
    --out $signed $Apk
if ($LASTEXITCODE -ne 0) { throw "apksigner sign failed with exit code $LASTEXITCODE" }
Move-Item -LiteralPath $signed -Destination $Apk -Force
