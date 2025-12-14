@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d C:\work\daily-tech-trend

if not exist logs mkdir logs

REM JSTで日付ファイル名（PowerShellで生成） - クォート崩れに強い書き方
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format ''yyyyMMdd_HHmmss''"') do set "TS=%%i"
set "LOG=logs\run_%TS%.log"

set "LASTSTEP=init"
set "FAILCODE="

echo ==== Daily Tech Trend start %date% %time% ==== > "%LOG%"
echo BAT=%~f0 >> "%LOG%"
echo CWD=%CD% >> "%LOG%"
where python >> "%LOG%" 2>&1
where py >> "%LOG%" 2>&1

REM -------- Python --------
set "LASTSTEP=collect"
py -3.11 src\collect.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=normalize"
py -3.11 src\normalize.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=normalize_categories"
py -3.11 src\normalize_categories.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=dedupe"
py -3.11 src\dedupe.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=thread"
py -3.11 src\thread.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=translate"
py -3.11 src\translate.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=llm_insights_local"
py -3.11 src\llm_insights_local.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=render"
py -3.11 src\render.py >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=check_output"
if not exist docs\index.html (
  echo docs/index.html not found >> "%LOG%"
  set "FAILCODE=2"
  goto :fail
)

REM -------- Git --------
set "LASTSTEP=git_add"
git add docs\index.html >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

set "LASTSTEP=git_diff"
git diff --cached --quiet >> "%LOG%" 2>&1
set "DIFFRC=!ERRORLEVEL!"

if "!DIFFRC!"=="0" (
  echo No changes: docs/index.html >> "%LOG%"
) else if "!DIFFRC!"=="1" (

  set "LASTSTEP=git_commit"
  git commit -m "daily update (local LLM)" >> "%LOG%" 2>&1
  set "RC=!ERRORLEVEL!"
  if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

  set "LASTSTEP=git_pull_rebase"
  git pull --rebase >> "%LOG%" 2>&1
  set "RC=!ERRORLEVEL!"
  if not "!RC!"=="0" ( set "FAILCODE=!RC!" & goto :fail )

  REM pushはネットワーク不調等に備えて2回リトライ
  set "LASTSTEP=git_push"
  set "PUSH_RC=1"
  for /l %%n in (1,1,2) do (
    git push >> "%LOG%" 2>&1
    set "PUSH_RC=!ERRORLEVEL!"
    if "!PUSH_RC!"=="0" goto push_ok
    echo [WARN] git push failed try=%%n rc=!PUSH_RC! >> "%LOG%"
    timeout /t 5 >nul
  )

  REM 2回失敗したらfail
  set "FAILCODE=!PUSH_RC!"
  goto :fail

  :push_ok
  REM push成功時は何もしないで次へ

) else (
  echo Git diff failed (rc=!DIFFRC!) >> "%LOG%"
  set "FAILCODE=!DIFFRC!"
  goto :fail
)

REM -------- Cleanup (失敗しても止めない) --------
set "LASTSTEP=cleanup"
dir /b logs\run_*.log >nul 2>nul
if "!ERRORLEVEL!"=="0" (
  forfiles /p logs /m run_*.log /d -30 /c "cmd /c del @path" >> "%LOG%" 2>nul
  set "RC=!ERRORLEVEL!"
  if not "!RC!"=="0" (
    echo [WARN] forfiles failed rc=!RC! >> "%LOG%"
    cmd /c exit 0
  )
) else (
  echo No log files to cleanup >> "%LOG%"
)

set "LASTSTEP=success"
cmd /c exit 0
echo ==== SUCCESS_FROM_BAT %date% %time% ==== >> "%LOG%"
exit /b 0

:fail
if not defined FAILCODE set "FAILCODE=!ERRORLEVEL!"
echo ==== FAILED_FROM_BAT step=%LASTSTEP% rc=%FAILCODE% %date% %time% ==== >> "%LOG%"
echo ==== FAILED_FROM_BAT step=%LASTSTEP% rc=%FAILCODE% %date% %time% ====
exit /b 1
