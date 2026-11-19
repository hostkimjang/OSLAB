$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = 'C:\OSLabWall'
$downloads = Join-Path $root 'downloads'
$apps = Join-Path $root 'apps'
New-Item -ItemType Directory -Path $downloads,$apps -Force | Out-Null
$progressFile = Join-Path $root 'packages-status.json'
$results = [ordered]@{}
$entries = @(
    @('7zip','msi','https://github.com/ip7z/7zip/releases/download/26.06/7z2606-x64.msi','6dc822569e777d9a3ecd5ffcbc22b55600af87e6c5d9810a64e8566cf5a4af9f'),
    @('libreoffice','msi','https://download.documentfoundation.org/libreoffice/stable/26.8.3/win/x86_64/LibreOffice_26.8.3_Win_x86-64.msi','0e6918c273eabbdbbd800ee0dacbbf130a14c13c2e4cec861b06dd59e015bf94'),
    @('obs','zip','https://cdn-fastly.obsproject.com/downloads/OBS-Studio-33.0.1-Windows-x64.zip','0d9436451c2d772b33428e3fdae9776f071895c335de17283176306fb72651d3'),
    @('notepadpp','zip','https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.9.1/npp.8.9.9.1.portable.x64.zip','cbcefa34677e10fe6dd19802f7d6b3b9860cd6de62afeaae7680e09c51b47779'),
    @('git','7z','https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/PortableGit-2.56.1-64-bit.7z.exe','9dd04a608ceb5f6ab32a73709e0ecb159d211da71b697c45ff81f6dd0c6b49c7'),
    @('sqlitebrowser','zip','https://github.com/sqlitebrowser/sqlitebrowser/releases/download/v3.13.1/DB.Browser.for.SQLite-v3.13.1-win64.zip','22375e275ec42d96de1d3b8e9ea4ed86d2a3505c4d0ffcbd1af67aa4003e5e4d'),
    @('winmerge','zip','https://github.com/WinMerge/winmerge/releases/download/v2.16.60/winmerge-2.16.60-x64-exe.zip','be3f850ed2e450c474928ccb67d2998e812da90dea1240a46352714553342522'),
    @('vlc','7z','https://download.videolan.org/pub/videolan/vlc/3.0.23/win64/vlc-3.0.23-win64.7z','eb4fd8a28291da73608c733786a09610fea865fbe94113bcb60b91c1ebb8404a'),
    @('audacity','msi','https://github.com/audacity/audacity/releases/download/Audacity-4.0.2/audacity-win-4.0.2-x86_64.msi','ff6cad670befee96fee563056965fa5e17bfa8c7ea3aba10c461c18799409e22'),
    @('shotcut','zip','https://github.com/mltframework/shotcut/releases/download/v26.11.15/shotcut-win64-26.11.15.zip','d704c12a8ce6d1fbe1a13155578ee5cf36b749a26503500cce38d8e68f900b0d'),
    @('ilspy','zip','https://github.com/icsharpcode/ILSpy/releases/download/v11.2/ILSpy_windows_selfcontained_11.2.0.10050-x64.zip','c30cda0e5a22435df5013eeffa515594abf144e2d06c9bb5ddcc9fccdefd69c8'),
    @('sumatra','zip','https://www.sumatrapdfreader.org/dl/rel/3.6.1/SumatraPDF-3.6.1-64.zip',''),
    @('everything','zip','https://www.voidtools.com/Everything-1.4.1.1032.x64.en-US.zip','705e0b46c6cbf74bd6082a6ebf77afac526868db9d7578f5dc1447f459484611'),
    @('procmon','zip','https://download.sysinternals.com/files/ProcessMonitor.zip',''),
    @('procexp','zip','https://download.sysinternals.com/files/ProcessExplorer.zip',''),
    @('tcpview','zip','https://download.sysinternals.com/files/TCPView.zip',''),
    @('vmmap','zip','https://download.sysinternals.com/files/VMMap.zip','')
)

function Save-Stage {
    [IO.File]::WriteAllText($progressFile,($results | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
}

function Start-Download($Entry) {
    $name,$format,$url,$sha = $Entry
    $path = Join-Path $downloads "$name.$format"
    $args = '-fsSL --retry 2 --retry-delay 1 --connect-timeout 20 --max-time 340 -o "{0}" "{1}"' -f $path,$url
    $child = Start-Process curl.exe -ArgumentList $args -WindowStyle Hidden -PassThru
    [pscustomobject]@{name=$name; format=$format; path=$path; sha=$sha; process=$child; source=$url}
}

function Install-Package($Job) {
    $Job.process.WaitForExit()
    if ($Job.process.ExitCode -ne 0) { throw "Download failed ($($Job.process.ExitCode))" }
    $sha = (Get-FileHash -LiteralPath $Job.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Job.sha -and $sha -ne $Job.sha) { throw 'Installer hash mismatch' }
    if ($Job.format -eq 'msi') {
        $argv='/i "{0}" /qn /norestart /l*v "{1}"' -f $Job.path,(Join-Path $downloads ("$($Job.name).log"))
        $installer=Start-Process msiexec.exe -ArgumentList $argv -PassThru -Wait -WindowStyle Hidden
        if ($installer.ExitCode -notin @(0,3010)) { throw "MSI failed ($($installer.ExitCode))" }
    } else {
        $target=Join-Path $apps $Job.name
        New-Item -Path $target -ItemType Directory -Force | Out-Null
        if ($Job.format -eq 'zip') {
            & tar.exe -xf $Job.path -C $target
        } else {
            & "$env:ProgramFiles\7-Zip\7z.exe" x $Job.path ('-o'+$target) -y | Out-Null
        }
        if ($LASTEXITCODE -ne 0) { throw "Unpack failed ($LASTEXITCODE)" }
        if ($Job.name -in @('procmon','procexp','tcpview','vmmap')) {
            $signed=@(Get-ChildItem -LiteralPath $target -Filter *.exe -Recurse | Where-Object {
                (Get-AuthenticodeSignature -LiteralPath $_.FullName).SignerCertificate.Subject -like '*Microsoft Corporation*'
            })
            if (!$signed.Count) { throw 'Microsoft executable signature not found' }
        }
    }
    $results[$Job.name] = @{status='installed';sha256=$sha;source=$Job.source}
}

$jobs = @()
try {
    $jobs = @($entries | ForEach-Object { Start-Download $_ })
    foreach ($job in $jobs) {
        try { Install-Package $job }
        catch { $results[$job.name] = @{status='error';reason=$_.Exception.Message} }
        Save-Stage
    }

    $winget = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
    foreach ($entry in @(
        @('vscode','Microsoft.VisualStudioCode'), @('python','Python.Python.3.14'),
        @('inkscape','Inkscape.Inkscape'), @('imagemagick','ImageMagick.ImageMagick')
    )) {
        $name,$id=$entry
        try {
            $arguments = "install --exact --id $id --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity --scope machine"
            $install=Start-Process -FilePath $winget -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
            $results[$name] = @{status=if($install.ExitCode -eq 0){'installed'}else{'error'}; id=$id; exitCode=$install.ExitCode}
        } catch { $results[$name]=@{status='error';id=$id;reason=$_.Exception.Message} }
        Save-Stage
    }
} finally {
    [IO.File]::WriteAllText((Join-Path $root 'packages-finished.ok'),'finished')
}
