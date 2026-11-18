$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\OSLabWall'
$updated=[ordered]@{}
$todo=@(
    @('winmerge','https://github.com/WinMerge/winmerge/releases/download/v2.16.60/winmerge-2.16.60-x64-exe.zip','be3f850ed2e450c474928ccb67d2998e812da90dea1240a46352714553342522'),
    @('vlc','https://ftp.osuosl.org/pub/videolan/vlc/3.0.23/win64/vlc-3.0.23-win64.zip','992d19dbd0b8a7cde9167d2f7780b1ef6f92acc8a71acfa736101a21f35181e1')
)
foreach ($entry in $todo) {
    $name,$url,$hash=$entry
    try {
        $zip=Join-Path $root "downloads\retry-$name.zip"
        & curl.exe -fsSL --retry 1 --connect-timeout 16 --max-time 180 -o $zip $url
        if ($LASTEXITCODE -ne 0) { throw "Download failed with $LASTEXITCODE" }
        $actual=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $hash) { throw "Vendor hash differs: $actual" }
        $target=Join-Path $root "apps\$name"
        New-Item -Path $target -ItemType Directory -Force | Out-Null
        & tar.exe -xf $zip -C $target
        if ($LASTEXITCODE -ne 0) { throw "Archive extraction failed with $LASTEXITCODE" }
        $updated[$name]=@{status='installed';sha256=$actual;source=$url}
    } catch {
        $updated[$name]=@{status='error';reason=$_.Exception.Message}
    }
    [IO.File]::WriteAllText((Join-Path $root 'packages-retry.json'),($updated | ConvertTo-Json -Compress))
}
