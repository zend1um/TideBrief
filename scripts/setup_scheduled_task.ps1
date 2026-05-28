# Windows 任务计划：每日 4:55 触发信息采集
# 以管理员身份运行此脚本

$TaskName = "InfoCollectorDailyCrawl"
$Description = "每日 4:55 运行政治经济信息采集管道"
$ScriptPath = "E:\proj\infoCollector\run.bat"

# 创建 run.bat（激活 conda 环境并运行 main.py）
@"
@echo off
call G:\Miniconda\Scripts\activate.bat infocollector
cd /d E:\proj\infoCollector
python main.py run >> logs\scheduled_%date:~0,10%.log 2>&1
"@ | Out-File -FilePath $ScriptPath -Encoding ASCII

# 创建计划任务
$Action = New-ScheduledTaskAction -Execute $ScriptPath
$Trigger = New-ScheduledTaskTrigger -Daily -At 04:55
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Description $Description `
    -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings `
    -Force

Write-Host "Task '$TaskName' registered. Next run: 04:55 daily."
Write-Host "Check in Task Scheduler (taskschd.msc) to verify."
