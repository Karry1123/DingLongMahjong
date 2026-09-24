param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,
    [string]$CommitMessage = "Prepare Mahjong EV cloud deployment"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

# Trust this exact workspace only for each Git invocation.
$trustedDirectory = $projectRoot.Replace("\", "/")

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".git"))) {
    git -c "safe.directory=$trustedDirectory" init -b main
    if ($LASTEXITCODE -ne 0) { throw "Could not initialize the Git repository" }
}

git -c "safe.directory=$trustedDirectory" add --all
if ($LASTEXITCODE -ne 0) { throw "Could not stage files" }
# Existing Markdown uses two trailing spaces for hard line breaks.
git -c "safe.directory=$trustedDirectory" -c "core.whitespace=-blank-at-eol,-blank-at-eof" diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Staged changes failed git diff --check" }

$tracked = @(git -c "safe.directory=$trustedDirectory" ls-files --cached)
$forbidden = @($tracked | Where-Object {
    $_ -match '(^|/)(\.env(\.local|\.[^/]+\.local)?|node_modules|\.venv|venv|dist|__pycache__|game_logs)(/|$)' -or
    $_ -match '(^|/)tests/artifacts(/|$)' -or
    $_ -match '\.(pem|key|mp4|mov|wav|psd)$'
})
if ($forbidden.Count -gt 0) {
    throw "Staged files include generated or sensitive paths: $($forbidden -join ', ')"
}

git -c "safe.directory=$trustedDirectory" diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git -c "safe.directory=$trustedDirectory" commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { throw "Commit failed; check git user.name and user.email" }
} elseif ($LASTEXITCODE -ne 0) {
    throw "Could not inspect staged changes"
}

$branch = (git -c "safe.directory=$trustedDirectory" branch --show-current).Trim()
if (-not $branch) { throw "Could not determine the current branch" }
$remoteNames = @(git -c "safe.directory=$trustedDirectory" remote)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect Git remotes" }
if ($remoteNames -contains "origin") {
    $origin = git -c "safe.directory=$trustedDirectory" remote get-url origin
    if ($LASTEXITCODE -ne 0) { throw "Could not read the origin remote" }
    if ($origin.Trim() -ne $RepositoryUrl) {
        throw "Existing origin is $origin; verify the repository URL"
    }
} else {
    git -c "safe.directory=$trustedDirectory" remote add origin $RepositoryUrl
    if ($LASTEXITCODE -ne 0) { throw "Could not add the origin remote" }
}

git -c "safe.directory=$trustedDirectory" push -u origin $branch
if ($LASTEXITCODE -ne 0) { throw "Push failed; check the GitHub URL and authentication" }
