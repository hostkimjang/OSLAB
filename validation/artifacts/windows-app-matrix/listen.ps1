[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$directory = $PSScriptRoot
$listener = [Net.HttpListener]::new()
$listener.Prefixes.Add('http://127.0.0.1:7788/')
$listener.Start()
try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        try {
            $path = $request.Url.AbsolutePath
            if ($request.HttpMethod -eq 'GET' -and $path -eq '/') {
                $body = [IO.File]::ReadAllBytes((Join-Path $directory 'app.html'))
                $response.ContentType = 'text/html; charset=utf-8'
                $response.ContentLength64 = $body.Length
                $response.OutputStream.Write($body, 0, $body.Length)
            } elseif ($request.HttpMethod -eq 'GET' -and $path -eq '/health') {
                $response.StatusCode = 204
            } elseif ($request.HttpMethod -eq 'POST' -and $path -match '^/evidence/([0-3])$' -and
                      $request.ContentLength64 -gt 0 -and $request.ContentLength64 -le 65536) {
                $phase = [int]$Matches[1]
                $reader = [IO.StreamReader]::new($request.InputStream, [Text.Encoding]::UTF8)
                try { $body = $reader.ReadToEnd() } finally { $reader.Dispose() }
                $record = $body | ConvertFrom-Json
                if ($record.step -ne $phase -or $record.id -notmatch '^\d{2}$') { throw 'Invalid capture evidence' }
                $file = Join-Path $directory "evidence-$phase.json"
                $temp = "$file.new"
                [IO.File]::WriteAllText($temp, $body, [Text.UTF8Encoding]::new($false))
                Move-Item -LiteralPath $temp -Destination $file -Force
                $response.StatusCode = 204
            } else {
                $response.StatusCode = 404
            }
        } catch {
            $response.StatusCode = 400
        } finally {
            $response.Close()
        }
    }
} finally {
    $listener.Close()
}
