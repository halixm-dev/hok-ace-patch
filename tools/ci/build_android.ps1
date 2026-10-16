# Build every pinned ARM64 codec on a clean Windows runner, then verify the APK.
param(
    [ValidateSet('Debug', 'Release')][string]$Variant = 'Debug',
    [string]$VersionName = '0.1-ci',
    [int]$VersionCode = 1
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Resolve-Path "$PSScriptRoot/../..")

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

$python = (Resolve-Path '.venv/Scripts/python.exe').Path
$sdk = $env:ANDROID_HOME
if (-not $sdk) { throw 'ANDROID_HOME is required' }
$ndk = Join-Path $sdk 'ndk/28.2.13676358'
$cmake = Join-Path $sdk 'cmake/3.22.1'
$work = Join-Path $env:RUNNER_TEMP 'hok-ace-native'
New-Item -ItemType Directory -Force $work, artifacts | Out-Null
$target = Join-Path $work 'target-3.12.12-0-arm64-v8a.zip'
Invoke-WebRequest 'https://chaquo.com/maven/com/chaquo/python/target/3.12.12-0/target-3.12.12-0-arm64-v8a.zip' -OutFile $target
if ((Get-FileHash $target -Algorithm SHA256).Hash -ne '7A4A278EC1FED0E0D0359FBEC71D6D481D79A7EFBC8E2090267A91046417027A') {
    throw 'Chaquopy Python target checksum mismatch'
}
Invoke-Checked $python @('android/native/build_wheels.py', '--ndk', $ndk, '--python-target', $target, '--work', "$work/codecs", '--output', 'android/wheels')
Invoke-Checked $python @('android/native/build_compression_wheels.py', '--ndk', $ndk, '--python-headers', "$work/codecs/python-target/include/python3.12", '--python-libs', "$work/codecs/python-target/jniLibs/arm64-v8a", '--work', "$work/dependencies", '--output', 'android/wheels')
Invoke-Checked $python @('android/native/build_freetype_wheel.py', '--ndk', $ndk, '--cmake', $cmake, '--work', "$work/dependencies", '--output', 'android/wheels')
Invoke-Checked './android/gradlew.bat' @('-p', 'android', '--no-daemon', ":app:assemble$Variant", ':app:testDebugUnitTest', ':app:lintDebug', ':app:writeRuntimeDependencyInventory', "-PpatchVersionName=$VersionName", "-PpatchVersionCode=$VersionCode")
$apk = "android/app/build/outputs/apk/$($Variant.ToLower())/app-$($Variant.ToLower()).apk"
if (-not (Test-Path $apk)) { throw 'Expected signed APK is missing' }
Invoke-Checked $python @('tools/research/check_android_native.py', $apk, '--report', 'artifacts/android-native-alignment.json')
Invoke-Checked "$sdk/build-tools/35.0.0/zipalign.exe" @('-c', '-P', '16', '4', $apk)
Invoke-Checked "$sdk/build-tools/35.0.0/apksigner.bat" @('verify', '--verbose', '--print-certs', $apk)
Invoke-Checked $python @('android/native/package_sources.py', '--sources', "$work/codecs", '--compression-sources', "$work/dependencies", '--freetype-sources', "$work/dependencies", '--output', 'artifacts/hok-ace-patch-codec-sources.zip')
Copy-Item $apk 'artifacts/hok-ace-patch.apk'
$hash = (Get-FileHash artifacts/hok-ace-patch.apk -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content artifacts/SHA256SUMS "$hash  hok-ace-patch.apk" -Encoding ascii
