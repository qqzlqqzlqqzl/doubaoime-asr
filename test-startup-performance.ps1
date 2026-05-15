param(
  [string]$ExePath = "",
  [int]$Runs = 3,
  [int]$TargetMs = 500,
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

if ($ExePath -eq "") {
  $InstalledExe = Join-Path $env:LOCALAPPDATA "DoubaoASRHelper\DoubaoASRHelper.exe"
  $DistExe = Join-Path $PSScriptRoot "dist\DoubaoASRHelper.exe"
  if (Test-Path $InstalledExe) {
    $ExePath = $InstalledExe
  }
  elseif (Test-Path $DistExe) {
    $ExePath = $DistExe
  }
}

if (-not (Test-Path $ExePath)) {
  throw "DoubaoASRHelper.exe not found. Pass -ExePath or build/install the app first."
}

$ExePath = (Resolve-Path $ExePath).Path
$ReportsDir = Join-Path $PSScriptRoot "release\test-reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
if ($ReportPath -eq "") {
  $ReportPath = Join-Path $ReportsDir "startup-performance.json"
}

if (-not ([System.Management.Automation.PSTypeName]'DoubaoStartupWin32').Type) {
  Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public struct DoubaoStartupRect {
  public int Left;
  public int Top;
  public int Right;
  public int Bottom;
}

public class DoubaoStartupWin32 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out DoubaoStartupRect rect);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, StringBuilder lParam);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

  public static string GetWindowTitle(IntPtr hWnd) {
    StringBuilder text = new StringBuilder(256);
    GetWindowText(hWnd, text, text.Capacity);
    return text.ToString();
  }

  public static string GetControlText(IntPtr hWnd) {
    int length = (int)SendMessage(hWnd, 0x000E, IntPtr.Zero, IntPtr.Zero);
    StringBuilder text = new StringBuilder(Math.Max(256, length + 1));
    SendMessage(hWnd, 0x000D, (IntPtr)text.Capacity, text);
    return text.ToString();
  }

  public static IntPtr FindVisibleWindow(int expectedProcessId, string titleContains) {
    IntPtr result = IntPtr.Zero;
    EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
      if (!IsWindowVisible(hWnd)) return true;
      uint pid;
      GetWindowThreadProcessId(hWnd, out pid);
      if (pid != expectedProcessId) return true;
      string title = GetWindowTitle(hWnd);
      if (title == null || !title.Contains(titleContains)) return true;
      result = hWnd;
      return false;
    }, IntPtr.Zero);
    return result;
  }

  public static int[] GetRect(IntPtr hWnd) {
    DoubaoStartupRect rect;
    if (!GetWindowRect(hWnd, out rect)) return new int[0];
    return new int[] { rect.Left, rect.Top, rect.Right, rect.Bottom };
  }

  public static string[] GetChildTexts(IntPtr hWnd) {
    System.Collections.Generic.List<string> texts = new System.Collections.Generic.List<string>();
    if (hWnd == IntPtr.Zero) return texts.ToArray();
    EnumChildWindows(hWnd, delegate(IntPtr child, IntPtr lParam) {
      string text = GetControlText(child);
      if (!String.IsNullOrWhiteSpace(text)) texts.Add(text);
      return true;
    }, IntPtr.Zero);
    return texts.ToArray();
  }
}
"@
}

function Stop-DoubaoProcesses {
  Get-Process DoubaoASRHelper, asr_bridge -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
}

function Reset-RunAppData {
  param([string]$Path)

  $reportsFull = [System.IO.Path]::GetFullPath($ReportsDir)
  $pathFull = [System.IO.Path]::GetFullPath($Path)
  if (-not $pathFull.StartsWith($reportsFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove APPDATA outside reports dir: $Path"
  }
  Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

$ExpectedTexts = @(
  "【按着说】模式",
  "【自由说】模式",
  "【按着说+自动发送】模式",
  "高级设置",
  "保存",
  "取消",
  "状态: ● 已就绪"
)

$Results = @()
Stop-DoubaoProcesses

for ($i = 1; $i -le $Runs; $i++) {
  $runName = "startup-performance-appdata-$i"
  $runAppData = Join-Path $ReportsDir $runName
  Reset-RunAppData -Path $runAppData

  $oldAppData = $env:APPDATA
  $env:APPDATA = $runAppData
  $process = $null
  $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    $process = Start-Process -FilePath $ExePath -PassThru
    $ready = $false
    $missing = @($ExpectedTexts)
    $rect = @()
    $texts = @()
    $deadline = (Get-Date).AddSeconds(5)

    while ((Get-Date) -lt $deadline) {
      if ($process.HasExited) {
        break
      }

      $window = [DoubaoStartupWin32]::FindVisibleWindow($process.Id, "豆包语音助手 - 设置")
      if ($window -ne [IntPtr]::Zero) {
        $texts = @([DoubaoStartupWin32]::GetChildTexts($window))
        $joined = $texts -join "`n"
        $missing = @($ExpectedTexts | Where-Object { -not $joined.Contains($_) })
        if ($missing.Count -eq 0) {
          $stopwatch.Stop()
          $rect = @([DoubaoStartupWin32]::GetRect($window))
          $ready = $true
          break
        }
      }
      Start-Sleep -Milliseconds 20
    }

    if (-not $ready -and $stopwatch.IsRunning) {
      $stopwatch.Stop()
    }

    $elapsed = [int][Math]::Round($stopwatch.Elapsed.TotalMilliseconds)
    $Results += [ordered]@{
      name = $runName
      visible_ms = $elapsed
      ok = ($ready -and $elapsed -le $TargetMs)
      ui_ready = $ready
      missing_texts = @($missing)
      rect = @($rect)
    }
  }
  finally {
    if ($process -ne $null -and -not $process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-DoubaoProcesses
    $env:APPDATA = $oldAppData
  }
}

$visibleValues = @($Results | ForEach-Object { [double]$_.visible_ms })
$Report = [ordered]@{
  target_ms = $TargetMs
  exe = $ExePath
  results = $Results
  min_ms = ($visibleValues | Measure-Object -Minimum).Minimum
  max_ms = ($visibleValues | Measure-Object -Maximum).Maximum
  avg_ms = ($visibleValues | Measure-Object -Average).Average
  ok = -not @($Results | Where-Object { -not $_.ok })
}

$Report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8

if (-not $Report.ok) {
  Write-Host "Startup performance failed. Report: $ReportPath"
  $Results | Format-Table -AutoSize
  exit 1
}

Write-Host "Startup performance passed. Report: $ReportPath"
$Results | Format-Table -AutoSize
