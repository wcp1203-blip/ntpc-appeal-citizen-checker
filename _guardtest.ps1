$ErrorActionPreference = 'SilentlyContinue'
$fail = $false

# 檢查 1：.kiro 是否被 git 忽略（競賽規範第 9 點）
git check-ignore -q .kiro
if ($LASTEXITCODE -eq 0) {
    Write-Output "[違規] .kiro 被 gitignore，違反競賽規範第 9 點"
    $fail = $true
}

# 檢查 2：是否有模組建立 bedrock-runtime client 卻未經過共用限流閘門
$pattern = 'client\(\s*["'']bedrock-runtime'
$files = Get-ChildItem -Path core, henry, lambda_handlers -Recurse -Filter *.py -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch 'bedrock_client\.py$' }
foreach ($f in $files) {
    $content = Get-Content -Raw -LiteralPath $f.FullName
    if ($content -match $pattern -and $content -notmatch 'throttle') {
        $rel = Resolve-Path -Relative $f.FullName
        Write-Output "[違規] $rel 建立 bedrock-runtime client 但未使用 throttle()，可能超過 1 RPS"
        $fail = $true
    }
}

if (-not $fail) { Write-Output "規範檢查通過" }
exit 0
