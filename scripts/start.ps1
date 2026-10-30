param([switch]$Production,[switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd([IO.Path]::DirectorySeparatorChar)
$rootPrefix=$projectRoot+[IO.Path]::DirectorySeparatorChar
Set-Location -LiteralPath $projectRoot
$pythonExe=[IO.Path]::GetFullPath((Join-Path $projectRoot '.venv\Scripts\python.exe'))
if(!$pythonExe.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $pythonExe -PathType Leaf)){throw 'Project Python is missing. Run scripts\setup.ps1 first.'}
# A normal clone uses Node installed on PATH. The optional portable-runtime
# pointer is retained only as a compatibility fallback for existing installs.
$nodeCommand=Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$nodeExe=if($nodeCommand){[IO.Path]::GetFullPath($nodeCommand.Source)}else{$null}
if(!$nodeExe){
 $nodePointer=Join-Path $projectRoot 'tools\node-path.txt'
 if(Test-Path -LiteralPath $nodePointer -PathType Leaf){
  $candidate=[IO.Path]::GetFullPath((Join-Path (Get-Content -LiteralPath $nodePointer -Raw).Trim() 'node.exe'))
  if(Test-Path -LiteralPath $candidate -PathType Leaf){$nodeExe=$candidate}
 }
}
if(!$nodeExe){throw 'Node.js is missing. Install Node.js 24 LTS, reopen PowerShell and run scripts\setup.ps1.'}
$nodeRoot=Split-Path -Parent $nodeExe
$nodeVersion=(& $nodeExe -p 'process.versions.node').Trim()
if($LASTEXITCODE -ne 0 -or [int]($nodeVersion.Split('.')[0]) -lt 24){throw 'Node.js 24 or later is required.'}
if(!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js') -PathType Leaf)){throw 'Frontend dependencies are missing. Run scripts\setup.ps1 first.'}
if($Production -and !(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html') -PathType Leaf)){throw 'Preview needs a frontend build. Run npm run build in frontend first.'}
$basePython=(& $pythonExe -c 'import ctypes; b=ctypes.create_unicode_buffer(32768); ctypes.windll.kernel32.GetModuleFileNameW(None,b,len(b)); print(b.value)').Trim()
if($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $basePython -PathType Leaf)){throw 'Cannot identify the virtual environment base interpreter.'}
$basePython=[IO.Path]::GetFullPath($basePython)
if($ValidateOnly){
 [ordered]@{status='ready';root=$projectRoot;python_executable=$pythonExe;base_python_executable=$basePython;node_executable=$nodeExe;node_version=$nodeVersion;no_processes_started=$true} | ConvertTo-Json -Depth 3
 exit 0
}
function Get-CommandHash([string]$value){
 $hash=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($value)))).Replace('-','').ToLowerInvariant()}
 finally{$hash.Dispose()}
}
function Get-Identity([int]$processIdentifier,[string]$role,[string]$kind){
 $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$processIdentifier" -ErrorAction Stop
 if(!$proc -or !$proc.ExecutablePath -or !$proc.CommandLine -or !$proc.CreationDate){throw "Cannot verify process $processIdentifier."}
 return [ordered]@{pid=[int]$proc.ProcessId;parent_pid=[int]$proc.ParentProcessId;role=$role;kind=$kind;executable=[IO.Path]::GetFullPath($proc.ExecutablePath);created_at_utc=$proc.CreationDate.ToUniversalTime().ToString('o');command_line=$proc.CommandLine;command_sha256=(Get-CommandHash $proc.CommandLine)}
}
function Assert-Identity($identity){
 $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$($identity.pid)" -ErrorAction SilentlyContinue
 if(!$proc){return $false}
 if(!$proc.ExecutablePath -or !$proc.CommandLine -or !$proc.CreationDate -or
 !([IO.Path]::GetFullPath($proc.ExecutablePath).Equals($identity.executable,[StringComparison]::OrdinalIgnoreCase)) -or
 $proc.CreationDate.ToUniversalTime().ToString('o') -ne $identity.created_at_utc -or (Get-CommandHash $proc.CommandLine) -ne $identity.command_sha256){throw "Process $($identity.pid) changed; refusing to stop it."}
 return $true
}
$records=[Collections.Generic.List[object]]::new()
function Add-VerifiedChildren{
 foreach($parent in @($records.ToArray() | Where-Object kind -eq 'launcher')){
  foreach($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($parent.pid)" -ErrorAction SilentlyContinue)){
   if($child.CommandLine -and $child.ExecutablePath -and (Get-CommandHash $child.CommandLine) -eq $parent.command_sha256 -and [IO.Path]::GetFullPath($child.ExecutablePath).Equals($basePython,[StringComparison]::OrdinalIgnoreCase)){
    if(!($records.ToArray() | Where-Object pid -eq $child.ProcessId)){$records.Add((Get-Identity $child.ProcessId $parent.role 'venv_child'))}
   }
  }
 }
}
function Get-OwnedListener([int]$port,$launcher,[string]$expectedExecutable){
 $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
 if($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1'){throw "Port $port is not exclusively bound to the expected loopback address."}
 $identity=Get-Identity $listeners[0].OwningProcess $launcher.role 'listener'
 if(($identity.pid -ne $launcher.pid -and $identity.parent_pid -ne $launcher.pid) -or $identity.command_sha256 -ne $launcher.command_sha256 -or !($identity.executable.Equals($expectedExecutable,[StringComparison]::OrdinalIgnoreCase))){throw "Port $port is not owned by the exact launched application."}
 if(!($records.ToArray() | Where-Object pid -eq $identity.pid)){$records.Add($identity)}
 return $identity
}
$env:PATH="$nodeRoot;$env:PATH"
$env:TEMP=Join-Path $projectRoot '.tmp'
$env:TMP=$env:TEMP
$env:npm_config_cache=Join-Path $projectRoot '.cache\npm'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$localSettings=Join-Path $projectRoot 'data\local-settings.json'
if(Test-Path -LiteralPath $localSettings -PathType Leaf){
 $profileValues=Get-Content -LiteralPath $localSettings -Raw | ConvertFrom-Json
 foreach($item in $profileValues.PSObject.Properties){
  if($item.Name -match '^KEDR_[A-Z0-9_]+$' -and [Environment]::GetEnvironmentVariable($item.Name,'Process') -eq $null -and $null -ne $item.Value){
   [Environment]::SetEnvironmentVariable($item.Name,[string]$item.Value,'Process')
  }
 }
}
$ownEnv=Join-Path $projectRoot '.env'
if(Test-Path -LiteralPath $ownEnv){
 foreach($line in Get-Content -LiteralPath $ownEnv){
  if($line -match '^\s*(KEDR_[A-Z0-9_]+)=(.*)$'){[Environment]::SetEnvironmentVariable($Matches[1],$Matches[2].Trim().Trim('"'),'Process')}
 }
}
$runtime=Join-Path $projectRoot 'data\runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
foreach($port in @(8710,5173)){
 if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){throw "Port $port is occupied. No process was stopped. Inspect its owner or stop this project's verified session."}
}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
try{
 $api=Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8710','--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "api-$stamp.log") -RedirectStandardError (Join-Path $runtime "api-$stamp.err.log") -PassThru
 $apiIdentity=Get-Identity $api.Id 'api' 'launcher'
 if(!($apiIdentity.executable.Equals($pythonExe,[StringComparison]::OrdinalIgnoreCase))){throw 'API launcher executable mismatch.'}
 $records.Add($apiIdentity)
 if($Production){$viteArgs=@('node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','5173','--strictPort')}else{$viteArgs=@('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort')}
 $web=Start-Process -FilePath $nodeExe -ArgumentList $viteArgs -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "web-$stamp.log") -RedirectStandardError (Join-Path $runtime "web-$stamp.err.log") -PassThru
 $webIdentity=Get-Identity $web.Id 'web' 'launcher'
 if(!($webIdentity.executable.Equals($nodeExe,[StringComparison]::OrdinalIgnoreCase))){throw 'Web launcher executable mismatch.'}
 $records.Add($webIdentity)
 $healthy=$false
 for($attempt=0;$attempt -lt 20;$attempt++){
  try{
   $health=Invoke-RestMethod -Uri 'http://127.0.0.1:8710/api/health' -TimeoutSec 1
   $webHealth=Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 1
   if($health.status -eq 'ok' -and $health.application -eq 'KEDR' -and $webHealth.StatusCode -eq 200){$healthy=$true;break}
  }catch{}
  Start-Sleep -Milliseconds 250
 }
 if(!$healthy){throw 'The owned servers did not pass readiness within the bounded startup window.'}
 $apiListener=Get-OwnedListener 8710 $apiIdentity $basePython
 $webListener=Get-OwnedListener 5173 $webIdentity $nodeExe
 [ordered]@{schema_version=2;root=$projectRoot;started_at_utc=[DateTime]::UtcNow.ToString('o');mode=$(if($Production){'preview'}else{'development'});api_pid=$api.Id;web_pid=$web.Id;api_listener_pid=$apiListener.pid;web_listener_pid=$webListener.pid;base_python_executable=$basePython;node_executable=$nodeExe;processes=$records.ToArray()} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runtime 'server-pids.json') -Encoding utf8
}catch{
 $failure=$_
 try{
  Add-VerifiedChildren
  $candidates=@($records.ToArray() | Sort-Object created_at_utc -Descending)
  foreach($item in $candidates){[void](Assert-Identity $item)}
  foreach($item in $candidates){if(Assert-Identity $item){Stop-Process -Id $item.pid -ErrorAction Stop}}
 }catch{Write-Warning "Rollback could not verify every process: $($_.Exception.Message). No unverified process was stopped."}
 throw $failure
}
Write-Output 'KEDR ready: http://127.0.0.1:5173'
Write-Output 'API health: http://127.0.0.1:8710/api/health'
Write-Output "Verified launcher IDs: API $($api.Id), web $($web.Id); API listener $($apiListener.pid)."
