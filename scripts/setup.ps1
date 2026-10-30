param([switch]$SkipInstall)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $projectRoot

function Invoke-Checked([string]$executable,[string[]]$arguments){
 & $executable @arguments
 if($LASTEXITCODE -ne 0){throw "Command failed with exit code ${LASTEXITCODE}: $executable"}
}

$pythonExe=Join-Path $projectRoot '.venv\Scripts\python.exe'
if(!(Test-Path -LiteralPath $pythonExe -PathType Leaf)){
 $launcher=Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
 if($launcher){
  Invoke-Checked $launcher.Source @('-3.13','-m','venv',(Join-Path $projectRoot '.venv'))
 }else{
  $pythonCommand=Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if(!$pythonCommand){throw 'Install Python 3.13 with the Windows py launcher, reopen PowerShell and run setup again.'}
  Invoke-Checked $pythonCommand.Source @('-c',"import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 is required'")
  Invoke-Checked $pythonCommand.Source @('-m','venv',(Join-Path $projectRoot '.venv'))
 }
}
Invoke-Checked $pythonExe @('-c',"import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 is required'")

$nodeCommand=Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$nodeRoot=if($nodeCommand){Split-Path -Parent $nodeCommand.Source}else{$null}
if(!$nodeRoot){
 $nodePointer=Join-Path $projectRoot 'tools\node-path.txt'
 if(Test-Path -LiteralPath $nodePointer -PathType Leaf){
  $candidate=(Get-Content -LiteralPath $nodePointer -Raw).Trim()
  if(Test-Path -LiteralPath (Join-Path $candidate 'node.exe') -PathType Leaf){$nodeRoot=$candidate}
 }
}
if(!$nodeRoot){throw 'Install Node.js 24 LTS, reopen PowerShell and run setup again.'}
$env:PATH="$nodeRoot;$env:PATH"
$nodeExe=Join-Path $nodeRoot 'node.exe'
$npmExe=Join-Path $nodeRoot 'npm.cmd'
if(!(Test-Path -LiteralPath $npmExe -PathType Leaf)){throw 'npm.cmd was not found beside Node.js. Install the complete Node.js distribution.'}
Invoke-Checked $nodeExe @('-e',"if (Number(process.versions.node.split('.')[0]) < 24) process.exit(1)")

if(!$SkipInstall){
 Invoke-Checked $pythonExe @('-m','pip','install','-r',(Join-Path $projectRoot 'requirements.lock.txt'))
 Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
 try{Invoke-Checked $npmExe @('ci','--ignore-scripts')}finally{Pop-Location}
}

$ownEnv=Join-Path $projectRoot '.env'
if(!(Test-Path -LiteralPath $ownEnv -PathType Leaf)){
 Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination $ownEnv
}
# Migrations also run automatically on first API startup. Importing db alone
# initializes storage without starting a server or opening any market archive.
Invoke-Checked $pythonExe @('-c',"from backend.app.db import Database; Database('data').initialize(); print('Local database migrations applied.')")
Write-Output 'Setup complete. Existing .env and database records were preserved.'
Write-Output 'Start: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1'
