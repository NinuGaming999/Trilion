---
name: system-check
description: Report PC health: CPU, RAM, disk space, GPU, temperatures, running heavy apps.
---
Use run_shell with these PowerShell commands (one at a time) and summarize in plain words:
- RAM and CPU: powershell -c "Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory,TotalVisibleMemorySize; (Get-CimInstance Win32_Processor).LoadPercentage"
- Disk: powershell -c "Get-PSDrive -PSProvider FileSystem | Select Name,Used,Free"
- GPU: nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv
- Top apps: powershell -c "Get-Process | Sort WorkingSet -desc | Select -First 5 Name,@{n='MB';e={[int]($_.WorkingSet/1MB)}}"
Warn the user if disk space is under 10 percent or RAM is almost full.
