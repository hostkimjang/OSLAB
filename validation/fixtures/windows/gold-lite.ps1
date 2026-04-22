$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$manifest = @{
  schema_version = 1
  image_id = "gold-lite"
  fixtures = @(
    @{
      id = "known-registry-git"
      name_contains = "Git"
      required_sources = @("Registry")
      optional_sources = @("PE", "StartMenu")
      must_not_sources = @("Portable")
    }
  )
}

$manifest |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 "$root\expected_inventory.json"

Write-Host "gold-lite fixture manifest written to $root\expected_inventory.json"

