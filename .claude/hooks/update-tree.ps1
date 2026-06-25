$ErrorActionPreference = "Stop"
$Root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$Script = Join-Path $Root ".claude\scripts\tree_context.py"
try {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python $Script post-update --root $Root
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 $Script post-update --root $Root
    }
} catch {
    # Non-blocking after tool use.
    Write-Error "tree-context update failed: $($_.Exception.Message)"
    exit 0
}
