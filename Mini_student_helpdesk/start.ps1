$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$helpdeskVenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $helpdeskVenvPython) {
    $helpdeskPython = $helpdeskVenvPython
} else {
    $helpdeskPython = (Get-Command python -ErrorAction Stop).Source
}

Write-Host 'Student Helpdesk: http://127.0.0.1:8501/'
Write-Host 'Giu cua so nay mo trong khi su dung. Nhan Ctrl+C de dung.'
& $helpdeskPython -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.port 8501 --server.headless true
exit $LASTEXITCODE
