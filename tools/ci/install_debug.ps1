# Build a debug patcher with the patcher key and lineage, check it, and install it on a phone over USB.
# For device cycles from this PC; CI builds through build_android.ps1. Runs the unit tests first. Refuses
# to install while the patcher's worker runs, since an install kills it mid-patch.
#
#   tools\ci\install_debug.ps1 -VersionCode 89 [-Serial f15a72e]
#
# The keystore's password is read from the `.password` file beside it and stays in this process.
param(
    [Parameter(Mandatory)][int]$VersionCode,
    [string]$Serial = '',
    [string]$Keystore = (Join-Path $HOME '.hok-ace-signing/patcher-2026.p12'),
    [string]$Alias = 'hokacepatch',
    [string]$CertSha256 = '555f2ff48b44a98395f6c305df13f74122545ab4eb57bb8f8d4267bf300b8ae5'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Resolve-Path "$PSScriptRoot/../..")

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

$sdk = $env:ANDROID_HOME
if (-not $sdk) { throw 'ANDROID_HOME is required' }
$tools = "$sdk/build-tools/35.0.0"
$password = [IO.Path]::ChangeExtension($Keystore, '.password')
if (-not (Test-Path -LiteralPath $Keystore) -or -not (Test-Path -LiteralPath $password)) {
    throw "Keystore or its .password file is missing: $Keystore"
}
if ($Serial) { $env:ANDROID_SERIAL = $Serial }
$names = 'ANDROID_RELEASE_KEYSTORE', 'ANDROID_RELEASE_STORE_PASSWORD', 'ANDROID_RELEASE_KEY_ALIAS', 'ANDROID_RELEASE_KEY_PASSWORD'
try {
    $env:ANDROID_RELEASE_KEYSTORE = (Resolve-Path -LiteralPath $Keystore).Path
    $env:ANDROID_RELEASE_STORE_PASSWORD = (Get-Content -LiteralPath $password -Raw).Trim()
    $env:ANDROID_RELEASE_KEY_PASSWORD = $env:ANDROID_RELEASE_STORE_PASSWORD
    $env:ANDROID_RELEASE_KEY_ALIAS = $Alias
    Invoke-Checked './android/gradlew.bat' @('-p', 'android', '-q', ':app:testDebugUnitTest', ':app:assembleDebug', "-PpatchVersionCode=$VersionCode")
    $apk = (Resolve-Path 'android/app/build/outputs/apk/debug/app-debug.apk').Path
    & "$PSScriptRoot/sign_android.ps1" -Apk $apk
} finally {
    foreach ($name in $names) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
}

$badging = & "$tools/aapt2.exe" dump badging $apk | Select-Object -First 1
if ($badging -notmatch "versionCode='$VersionCode'") { throw "APK reports $badging" }
$certs = & "$tools/apksigner.bat" verify --print-certs $apk
if (-not ($certs -match "SHA-256 digest: $CertSha256")) { throw "APK is not signed with the patcher key: $certs" }

$services = adb shell dumpsys activity services dev.halixm.hokacepatcher
if ($LASTEXITCODE -ne 0) { throw 'adb cannot reach the phone' }
if ($services -match 'PatchWorkerService') { throw 'The patcher is working on the phone; install once it stops' }
$output = adb install -r $apk
if ($LASTEXITCODE -ne 0 -or -not ($output -match 'Success')) { throw "Install failed: $output" }
$installed = adb shell dumpsys package dev.halixm.hokacepatcher | Select-String -Pattern 'versionCode=(\d+)' | Select-Object -First 1
if ($installed.Matches[0].Groups[1].Value -ne "$VersionCode") { throw "Phone reports $installed" }
Write-Output "Installed debug $VersionCode, signed $($CertSha256.Substring(0, 8))..."
