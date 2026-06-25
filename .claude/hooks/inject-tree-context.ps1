$ErrorActionPreference = "Stop"
$Root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$Script = Join-Path $Root ".claude\scripts\tree_context.py"
$InputJson = [Console]::In.ReadToEnd()

function Invoke-PythonTreeContext($pythonCmd) {
    $InputJson | & $pythonCmd $Script inject --root $Root
}

try {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-PythonTreeContext "python"
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $InputJson | py -3 $Script inject --root $Root
    } else {
        Write-Output "<tree-context compact=`"true`">Python not found; tree context hook skipped.</tree-context>"
    }
} catch {
    # Do not block the user prompt if the hook fails.
    Write-Error "tree-context inject failed: $($_.Exception.Message)"
    exit 0
}
