#requires -RunAsAdministrator
<#
    Daily Tech Trend / Watchdog タスクの恒久対策適用スクリプト (PC2 向け)

    実行方法:
      1. 管理者 PowerShell を起動
      2. cd C:\work\daily-tech-trend
      3. powershell -ExecutionPolicy Bypass -File tasks\apply_task_scheduler_fixes.ps1

    適用内容:
      - Daily Tech Trend: ExecutionTimeLimit PT72H → PT2H、StartWhenAvailable 有効化
      - Daily Tech Trend: stale "Running" 状態のクリア
      - Watchdog Daily Tech Trend: 無効化されていた 30 分間隔トリガーを再有効化
#>

$ErrorActionPreference = 'Stop'

Write-Host '=== Phase 1-C: Daily Tech Trend タスク設定更新 ===' -ForegroundColor Cyan

# 1. stale Running 状態の解消
$state = (Get-ScheduledTask -TaskName 'Daily Tech Trend').State
Write-Host ("  現在の State = {0}" -f $state)
if ($state -eq 'Running') {
    Write-Host '  stale Running をクリアするため Stop-ScheduledTask を実行します'
    Stop-ScheduledTask -TaskName 'Daily Tech Trend'
    Start-Sleep -Seconds 2
}

# 2. Settings 更新
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew
Set-ScheduledTask -TaskName 'Daily Tech Trend' -Settings $settings | Out-Null

$after = (Get-ScheduledTask -TaskName 'Daily Tech Trend').Settings
Write-Host '  更新後:'
$after | Format-List DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable, ExecutionTimeLimit, MultipleInstances | Out-String | Write-Host

Write-Host ''
Write-Host '=== Phase 3-A: Watchdog Daily Tech Trend トリガー再有効化 ===' -ForegroundColor Cyan

$w = Get-ScheduledTask -TaskName 'Watchdog Daily Tech Trend'
$triggerBefore = $w.Triggers[0].Enabled
Write-Host ("  更新前の Trigger.Enabled = {0}" -f $triggerBefore)

foreach ($t in $w.Triggers) { $t.Enabled = $true }
Set-ScheduledTask -TaskName 'Watchdog Daily Tech Trend' -Trigger $w.Triggers | Out-Null

$w2 = Get-ScheduledTask -TaskName 'Watchdog Daily Tech Trend'
Write-Host ("  更新後の Trigger.Enabled = {0}" -f $w2.Triggers[0].Enabled)
Write-Host ("  NextRunTime = {0}" -f (Get-ScheduledTaskInfo -TaskName 'Watchdog Daily Tech Trend').NextRunTime)

Write-Host ''
Write-Host '=== 完了 ===' -ForegroundColor Green
Write-Host '次回 06:00 (Daily Tech Trend) / 30 分以内 (Watchdog) で新設定が有効になります。'
