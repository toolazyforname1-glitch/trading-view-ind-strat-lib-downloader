# Pause / resume the background harvester jobs.
#   .\tv_pause.ps1    -> suspend the pythonw workers (state kept, resumable)
#   .\tv_resume.ps1   -> resume them
param([switch]$Resume)

$ErrorActionPreference = "Continue"
$targets = @("tv_desc_scrape", "tv_desc_phase3", "tv_finalize2", "tv_deep_sweep",
             "tv_watchdog", "tv_finalize")

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ProcCtl {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr h);
  [DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr h);
  [DllImport("kernel32.dll")] public static extern bool GetExitCodeProcess(IntPtr h, out uint code);
}
"@

$ACCESS = 0x0C00   # PROCESS_SUSPEND_RESUME | PROCESS_QUERY_INFORMATION

$procs = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object {
        $cl = $_.CommandLine
        $cl -and ($targets | Where-Object { $cl -like "*$_*" })
    }

if (-not $procs) { "no matching workers running"; exit 0 }

foreach ($p in $procs) {
    $h = [ProcCtl]::OpenProcess($ACCESS, $false, [uint32]$p.ProcessId)
    if ($h -eq [IntPtr]::Zero) { "  pid=$($p.ProcessId) OpenProcess failed"; continue }
    if ($Resume) {
        [void][ProcCtl]::NtResumeProcess($h)
        "  RESUMED pid=$($p.ProcessId)"
    } else {
        [void][ProcCtl]::NtSuspendProcess($h)
        "  SUSPENDED pid=$($p.ProcessId)"
    }
    [void][ProcCtl]::CloseHandle($h)
}
"done ($($procs.Count) process(es))"
