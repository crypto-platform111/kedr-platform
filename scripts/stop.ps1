param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd([IO.Path]::DirectorySeparatorChar)
$rootPrefix=$projectRoot+[IO.Path]::DirectorySeparatorChar
$record=Join-Path $projectRoot 'data\runtime\server-pids.json'
if(!(Test-Path -LiteralPath $record)){Write-Output 'No owned server record.';exit 0}
$state=Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
if($state.schema_version -ne 2 -or !$state.processes -or !([IO.Path]::GetFullPath($state.root).Equals($projectRoot,[StringComparison]::OrdinalIgnoreCase))){throw 'The server record has no verified process identities. Refusing a PID-only stop; inspect and explicitly adopt the old session first.'}
function Get-CommandHash([string]$value){
 $hash=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($value)))).Replace('-','').ToLowerInvariant()}
 finally{$hash.Dispose()}
}
$pythonExe=[IO.Path]::GetFullPath((Join-Path $projectRoot '.venv\Scripts\python.exe'))
if(!$state.node_executable -or !$state.base_python_executable){throw 'The server record is missing runtime identities. Nothing has been stopped.'}
$nodeExe=[IO.Path]::GetFullPath($state.node_executable)
# System Node may legitimately live outside the checkout. Its exact executable,
# creation clock and command hash are still verified against the launch record.
$apiPattern='^"?' + [regex]::Escape($pythonExe) + '"?\s+-m\s+uvicorn\s+backend\.app\.main:app\s+--host\s+127\.0\.0\.1\s+--port\s+8710\s+--no-access-log\s*$'
$webPattern='^"?' + [regex]::Escape($nodeExe) + '"?\s+node_modules/vite/bin/vite\.js(?:\s+preview)?\s+--host\s+127\.0\.0\.1\s+--port\s+5173\s+--strictPort\s*$'
$verified=[Collections.Generic.List[object]]::new()
foreach($identity in @($state.processes | Sort-Object created_at_utc -Descending)){
 $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$identity.pid)" -ErrorAction SilentlyContinue
 if(!$proc){continue}
 $actualPath=if($proc.ExecutablePath){[IO.Path]::GetFullPath($proc.ExecutablePath)}else{''}
 $allowedPath=if($identity.role -eq 'api'){$actualPath.Equals($pythonExe,[StringComparison]::OrdinalIgnoreCase) -or $actualPath.Equals($state.base_python_executable,[StringComparison]::OrdinalIgnoreCase)}elseif($identity.role -eq 'web'){$actualPath.Equals($nodeExe,[StringComparison]::OrdinalIgnoreCase)}else{$false}
 $pattern=if($identity.role -eq 'api'){$apiPattern}else{$webPattern}
 if(!$allowedPath -or !$proc.CommandLine -or !$proc.CreationDate -or
 !($actualPath.Equals($identity.executable,[StringComparison]::OrdinalIgnoreCase)) -or
 $proc.CreationDate.ToUniversalTime().ToString('o') -ne $identity.created_at_utc -or
 (Get-CommandHash $proc.CommandLine) -ne $identity.command_sha256 -or $proc.CommandLine -notmatch $pattern){throw "Process $($identity.pid) identity no longer matches this application. Nothing has been stopped."}
 if(!($verified.ToArray() | Where-Object pid -eq $identity.pid)){$verified.Add($identity)}
}
if($ValidateOnly){
 [ordered]@{status='verified';schema_version=2;processes=@($verified.ToArray() | ForEach-Object {[ordered]@{pid=$_.pid;role=$_.role;kind=$_.kind}});no_processes_stopped=$true} | ConvertTo-Json -Depth 4
 exit 0
}
# Validate the complete set first, then recheck identities at the action boundary.
foreach($identity in $verified.ToArray()){
 $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$identity.pid)" -ErrorAction SilentlyContinue
 if(!$proc){continue}
 if(!$proc.ExecutablePath -or !([IO.Path]::GetFullPath($proc.ExecutablePath).Equals($identity.executable,[StringComparison]::OrdinalIgnoreCase)) -or
 !$proc.CreationDate -or $proc.CreationDate.ToUniversalTime().ToString('o') -ne $identity.created_at_utc -or
 !$proc.CommandLine -or (Get-CommandHash $proc.CommandLine) -ne $identity.command_sha256){throw "Process $($identity.pid) changed after validation; refusing to stop it."}
 Stop-Process -Id $identity.pid -ErrorAction Stop
}
$state | Add-Member -NotePropertyName stopped_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $record -Encoding utf8
Write-Output 'Verified KEDR server processes stopped. Other services were not targeted.'
