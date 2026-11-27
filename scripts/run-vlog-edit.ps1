# Run /vlog-edit headless with Claude Code CLI and record the stream (for measurements and screenshots).
#   pwsh -File scripts\run-vlog-edit.ps1 -Request "40秒くらい、のんびりした雰囲気で" -OutDir ..\localcut-private\runs
param(
    [string]$Request = '40秒くらい、のんびりした雰囲気で',
    [string]$OutDir = (Join-Path $PSScriptRoot '..\..\localcut-private\runs')
)
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $repo
New-Item -ItemType Directory -Force $OutDir | Out-Null
$body = (Get-Content -Raw -Encoding utf8 '.claude\commands\vlog-edit.md') -split "`n" | Select-Object -Skip 5
$prompt = ($body -join "`n").Replace('$ARGUMENTS', $Request)
# Shells started from inside another Claude app can inherit its host-auth variables; use the CLI's own login.
Get-ChildItem env: | Where-Object { $_.Name -like 'CLAUDE_*' -or $_.Name -like 'CLAUDECODE*' -or $_.Name -like 'ANTHROPIC_*' } |
    ForEach-Object { Remove-Item "env:$($_.Name)" }
$env:MCP_TOOL_TIMEOUT = '1200000'
$allowed = 'mcp__localcut__footage_status,mcp__localcut__get_edit_brief,mcp__localcut__submit_edit_plan,mcp__localcut__render_preview,mcp__localcut__review_render,mcp__localcut__egress_report'
$t0 = Get-Date
$prompt | claude -p --mcp-config .mcp.json --strict-mcp-config --allowedTools $allowed `
    --disallowedTools 'Read,Bash,Glob,Grep,Edit,Write,WebFetch,WebSearch' --output-format stream-json --verbose |
    Out-File -Encoding utf8 (Join-Path $OutDir 'vlog-edit.jsonl')
"exit=$LASTEXITCODE elapsed=$([int]((Get-Date) - $t0).TotalSeconds)s"
