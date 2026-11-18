"""Stage vendor binaries on a disposable source before recording offline clones."""

from argparse import ArgumentParser
import base64
import json
from pathlib import Path
import secrets
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.with_name("windows-app-matrix")))
from lab import Lab, ROOT, USER, READY


def stage(lab, task, filename):
    base = lab.ref("base")
    lab.verify(base)
    if lab.verify(base).get("template"):
        raise RuntimeError("Cannot install into a sealed source template")
    lab.upload(base, filename, (HERE / filename).read_bytes())
    lab.task(base, task, rf"& '{ROOT}\{filename}'")


def prepare(lab):
    assert not lab.owned and lab.client.get_vm_config(lab.source).get("template")
    source_nic = lab.client.get_vm_config(lab.source)["net0"]
    model, *options = source_nic.split(",")
    assert model.partition("=")[0] in ("virtio", "e1000", "rtl8139", "vmxnet3")
    new_mac = "02:" + ":".join(f"{byte:02X}" for byte in secrets.token_bytes(5))
    staging_nic = ",".join([model.partition("=")[0] + "=" + new_mac, *(opt for opt in options if opt != "link_down=1")])
    base = lab.create("base", lab.source, full=True)
    lab.verify(base)
    lab.client.request("PUT", f"{lab.api}/qemu/{base.vm_id}/config", {"net0": staging_nic})
    lab.wait(base, "$true", 200)
    password = "Win9!" + secrets.token_hex(22)
    lab.ps(base, rf"""
        New-Item -Path '{ROOT}' -ItemType Directory -Force | Out-Null
        $account=New-LocalUser -Name '{USER}' -Password (ConvertTo-SecureString '{password}' -AsPlainText -Force) -PasswordNeverExpires
        Add-LocalGroupMember -SID 'S-1-5-32-544' -Member $account
        $oobe='HKLM:\Software\Policies\Microsoft\Windows\OOBE'
        New-Item $oobe -Force | Out-Null
        New-ItemProperty $oobe DisablePrivacyExperience -Type DWord -Value 1 -Force | Out-Null
    """)
    lab.task(base, "OSLabMatrixLogin", rf"""
        $winlogon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
        Set-ItemProperty $winlogon AutoAdminLogon '0'
        if (Test-Path $winlogon) {{Remove-ItemProperty $winlogon DefaultPassword -ErrorAction SilentlyContinue}}
        Start-Sleep -Seconds 4
        [IO.File]::WriteAllText('{READY}','ready')
    """, logon=True)
    lab.autologon(base, password)
    lab.ps(base, "shutdown.exe /r /f /t 2")
    lab.wait(base, f"Test-Path '{READY}'", 250)
    report = lab.ps(base, """
        $internet=(Test-NetConnection -ComputerName 'github.com' -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded
        $winget=[bool](Get-AppxPackage -AllUsers -Name Microsoft.DesktopAppInstaller)
        @{internet=$internet; wingetPackage=$winget} | ConvertTo-Json -Compress
    """, timeout=35)
    print(report.stdout, flush=True)
    if not json.loads(report.stdout)["internet"]:
        raise RuntimeError("The isolated package source cannot reach the vendor downloads")
    stage(lab, "OSLabStageProducts", "stage_products.ps1")



def inspect_source(lab, *, seal_source):
    base = lab.ref("base")
    lab.verify(base)
    script = rf"""
        $root='{ROOT}'
        $apps=Join-Path $root 'apps'
        function Find-Binary($directory,$file) {{
            if (Test-Path -LiteralPath $directory) {{
                $found=Get-ChildItem -LiteralPath $directory -Filter $file -File -Recurse -ErrorAction SilentlyContinue |
                    Sort-Object FullName | Select-Object -First 1
                if ($found) {{ return $found.FullName }}
            }}
        }}
        $pf=$env:ProgramFiles
        $lo=Join-Path $pf 'LibreOffice\program'
        $locations=[ordered]@{{
            '7zip'=(Join-Path $pf '7-Zip\7zFM.exe')
            calc=Join-Path $lo 'scalc.exe'
            writer=Join-Path $lo 'swriter.exe'
            impress=Join-Path $lo 'simpress.exe'
            draw=Join-Path $lo 'sdraw.exe'
            obs=Find-Binary "$apps\obs" 'obs64.exe'
            notepadpp=Find-Binary "$apps\notepadpp" 'notepad++.exe'
            sqlitebrowser=Find-Binary "$apps\sqlitebrowser" 'DB Browser for SQLite.exe'
            winmerge=Find-Binary "$apps\winmerge" 'WinMergeU.exe'
            vlc=Find-Binary "$apps\vlc" 'vlc.exe'
            audacity=Find-Binary "$pf\Audacity" 'Audacity.exe'
            shotcut=Find-Binary "$apps\shotcut" 'shotcut.exe'
            ilspy=Find-Binary "$apps\ilspy" 'ILSpy.exe'
            sumatra=Find-Binary "$apps\sumatra" 'SumatraPDF*.exe'
            everything=Find-Binary "$apps\everything" 'Everything.exe'
            procmon=Find-Binary "$apps\procmon" 'Procmon64.exe'
            procexp=Find-Binary "$apps\procexp" 'procexp64.exe'
            tcpview=Find-Binary "$apps\tcpview" 'Tcpview64.exe'
            vmmap=Find-Binary "$apps\vmmap" 'vmmap64.exe'
            gitgui=Find-Binary "$apps\git\cmd" 'git.exe'
            vscode=Find-Binary "$pf\Microsoft VS Code" 'Code.exe'
            inkscape=Find-Binary "$pf\Inkscape" 'inkscape.exe'
            idle=$null
            imagemagick=$null
        }}
        if (!$locations.gitgui) {{ $locations.gitgui=Find-Binary "$apps\git" 'git.exe' }}
        if (!$locations.audacity) {{
            foreach ($dir in (Get-ChildItem -LiteralPath $pf -Directory -Filter 'Audacity*')) {{
                $locations.audacity=Find-Binary $dir.FullName 'Audacity*.exe'
            }}
        }}
        foreach ($dir in (Get-ChildItem -LiteralPath $pf -Directory -Filter 'Python*')) {{
            $locations.idle=Find-Binary $dir.FullName 'pythonw.exe'
        }}
        foreach ($dir in (Get-ChildItem -LiteralPath $pf -Directory -Filter 'ImageMagick*')) {{
            $locations.imagemagick=Find-Binary $dir.FullName 'magick.exe'
        }}
        foreach ($item in @(@('procmon','procmon.exe'),@('procexp','procexp.exe'),@('tcpview','tcpview.exe'),@('vmmap','vmmap.exe'))) {{
            if (!$locations[$item[0]]) {{ $locations[$item[0]]=Find-Binary (Join-Path $apps $item[0]) $item[1] }}
        }}
        $versions=[ordered]@{{}}
        $checked=[ordered]@{{}}
        foreach ($name in $locations.Keys) {{
            $file=$locations[$name]
            if ($file -and (Test-Path -LiteralPath $file -PathType Leaf)) {{
                $exe=Get-Item -LiteralPath $file
                $signature=if ($name -in @('procmon','procexp','tcpview','vmmap')) {{
                    (Get-AuthenticodeSignature -LiteralPath $file).Status.ToString()
                }} else {{ '' }}
                $checked[$name]=$file
                $versions[$name]=@{{executable=$exe.Name;version=$exe.VersionInfo.ProductVersion;signature=$signature}}
            }}
        }}
        $os=Get-CimInstance Win32_OperatingSystem
        $primary=Join-Path $root 'packages-status.json'
        $retry=Join-Path $root 'packages-retry.json'
        $report=@{{paths=$checked;missing=@($locations.Keys | Where-Object {{!$checked[$_]}}); versions=$versions;
            baseFinished=(Test-Path (Join-Path $root 'packages-finished.ok'));windows=$os.Version;
            primary=if(Test-Path $primary){{Get-Content -LiteralPath $primary -Raw | ConvertFrom-Json}}else{{@{{}}}};
            retry=if(Test-Path $retry){{Get-Content -LiteralPath $retry -Raw | ConvertFrom-Json}}else{{@{{}}}} }}
        $json=$report | ConvertTo-Json -Compress -Depth 8
        [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    """
    actual = json.loads(base64.b64decode(lab.ps(base, script, timeout=90).stdout.strip(), validate=True))
    print("Available aliases", sorted(actual["paths"]), flush=True)
    print("Missing aliases", actual["missing"], "Windows", actual["windows"], "staging task finished", actual["baseFinished"], flush=True)
    for name, info in actual["retry"].items():
        print("retake", name, info.get("status"), info.get("reason", ""), flush=True)
    for name, info in actual["primary"].items():
        if info.get("status") != "installed" and actual["retry"].get(name, {}).get("status") != "installed":
            print("staging", name, info.get("exitCode"), info.get("reason", ""), flush=True)
    (lab.output / "programs.json").write_text(json.dumps(actual["paths"], indent=2), encoding="utf-8")
    (lab.output / "program-inventory.json").write_text(json.dumps(actual, indent=2), encoding="utf-8")

    if seal_source:
        assert actual["baseFinished"] and not actual["missing"]
        for name in ("procmon", "procexp", "tcpview", "vmmap"):
            assert actual["versions"][name]["signature"] == "Valid", name
        config = lab.verify(base)
        assert config.get("net0") and not config.get("template")
        lab.client.request("PUT", f"{lab.api}/qemu/{base.vm_id}/config", {"delete": "net0"})
        assert not any(key.startswith("net") for key in lab.verify(base))
        lab.ps(base, rf"""
            if (Test-Path -LiteralPath '{READY}') {{ Remove-Item -LiteralPath '{READY}' }}
            shutdown.exe /s /f /t 2
        """)
        until = time.monotonic() + 110
        while lab.client.get_vm_status(base.vm_id)["status"] != "stopped":
            if time.monotonic() > until:
                raise TimeoutError("Product staging guest did not shut down")
            time.sleep(2)
        result = lab.client.request("POST", f"{lab.api}/qemu/{base.vm_id}/template")
        if isinstance(result, str):
            lab.client.wait_for_task(result)
        assert lab.verify(base).get("template")
        print("Official program source sealed and its network removed.", flush=True)

def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "inventory", "repair-packages", "seal"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template-vmid", type=int, required=True)
    parser.add_argument("--vmid-start", type=int, required=True)
    parser.add_argument("--vmid-end", type=int, required=True)
    args = parser.parse_args()
    lab = Lab(args)
    if args.operation == "prepare":
        prepare(lab)
    elif args.operation == "repair-packages":
        stage(lab, "OSLabRetryArchives", "retry_install.ps1")
    else:
        inspect_source(lab, seal_source=args.operation == "seal")


if __name__ == "__main__":
    main()
