$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$DistExe = Join-Path $Root "dist\DoubaoASRHelper.exe"
$SetupExe = Join-Path $Root "dist\DoubaoASRHelperSetup.exe"
$PortableExe = Join-Path $Root "release\DoubaoASRHelper-portable.exe"
$PortableZip = Join-Path $Root "release\DoubaoASRHelper-Portable.zip"
$ReleaseZip = Join-Path $Root "release\DoubaoASRHelper-Windows.zip"
$AppIcon = Join-Path $Root "doubaoime_asr\assets\app.ico"
$ReportsDir = Join-Path $Root "release\test-reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public class DoubaoWin32Capture {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  public static string GetWindowTitle(IntPtr hWnd) {
    StringBuilder text = new StringBuilder(256);
    GetWindowText(hWnd, text, text.Capacity);
    return text.ToString();
  }
  public static IntPtr FindWindowForProcess(int expectedProcessId, string titleContains, int minWidth, int minHeight) {
    IntPtr found = IntPtr.Zero;
    long foundArea = 0;
    EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
      uint windowProcessId;
      GetWindowThreadProcessId(hWnd, out windowProcessId);
      if (windowProcessId != (uint)expectedProcessId || !IsWindowVisible(hWnd)) {
        return true;
      }
      string title = GetWindowTitle(hWnd);
      if (!String.IsNullOrWhiteSpace(title) && (String.IsNullOrEmpty(titleContains) || title.Contains(titleContains))) {
        RECT rect;
        GetWindowRect(hWnd, out rect);
        int width = rect.Right - rect.Left;
        int height = rect.Bottom - rect.Top;
        long area = (long)width * (long)height;
        if (width >= minWidth && height >= minHeight && area > foundArea) {
          found = hWnd;
          foundArea = area;
        }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
[DoubaoWin32Capture]::SetProcessDPIAware() | Out-Null

$HwndTopMost = [IntPtr](-1)
$HwndNoTopMost = [IntPtr](-2)
$HwndBottom = [IntPtr](1)
$SwpShowWindow = [uint32]0x0040
$SwpNoActivate = [uint32]0x0010
$MainWindowTitle = [string]::Concat([char]0x8C46, [char]0x5305, " ASR ", [char]0x52A9, [char]0x624B)

function Assert-CustomAppIcon {
  param([Parameter(Mandatory = $true)][string]$ExePath)

  if (-not (Test-Path $AppIcon)) {
    throw "Missing bundled app icon: $AppIcon"
  }
  if ((Get-Item -LiteralPath $AppIcon).Length -lt 10000) {
    throw "Bundled app icon is too small to contain the multi-size custom icon: $AppIcon"
  }
  if (-not (Test-Path $ExePath)) {
    throw "Missing executable for icon check: $ExePath"
  }

  $Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($ExePath)
  if ($null -eq $Icon) {
    throw "Could not extract executable icon: $ExePath"
  }
  try {
    $Bitmap = $Icon.ToBitmap()
    try {
      $BluePixels = 0
      $GreenPixels = 0
      $LightPixels = 0
      for ($X = 0; $X -lt $Bitmap.Width; $X++) {
        for ($Y = 0; $Y -lt $Bitmap.Height; $Y++) {
          $Pixel = $Bitmap.GetPixel($X, $Y)
          if ($Pixel.A -lt 160) {
            continue
          }
          if ($Pixel.B -gt 150 -and $Pixel.G -gt 80 -and $Pixel.R -lt 120) {
            $BluePixels++
          }
          if ($Pixel.G -gt 170 -and $Pixel.R -lt 190 -and $Pixel.B -lt 230) {
            $GreenPixels++
          }
          if ($Pixel.R -gt 220 -and $Pixel.G -gt 220 -and $Pixel.B -gt 220) {
            $LightPixels++
          }
        }
      }
      if ($BluePixels -lt 20 -or $GreenPixels -lt 4 -or $LightPixels -lt 10) {
        throw "Executable icon does not look like the bundled Doubao ASR microphone icon: $ExePath"
      }
    }
    finally {
      $Bitmap.Dispose()
    }
  }
  finally {
    $Icon.Dispose()
  }
}

function Assert-ShortcutUsesAppIcon {
  param([Parameter(Mandatory = $true)][string]$TargetExe)

  $Python = Join-Path $Root ".venv\Scripts\python.exe"
  if (-not (Test-Path $Python)) {
    throw "Missing test Python: $Python"
  }
  $Shortcut = Join-Path $ReportsDir "shortcut-icon-test.lnk"
  Remove-Item -LiteralPath $Shortcut -Force -ErrorAction SilentlyContinue
  $OldShortcutPath = $env:DOUBAO_SHORTCUT_TEST_PATH
  $OldShortcutTarget = $env:DOUBAO_SHORTCUT_TEST_TARGET
  try {
    $env:DOUBAO_SHORTCUT_TEST_PATH = $Shortcut
    $env:DOUBAO_SHORTCUT_TEST_TARGET = $TargetExe
    & $Python -c "import os; from pathlib import Path; from windows_installer import create_shortcut; create_shortcut(Path(os.environ['DOUBAO_SHORTCUT_TEST_PATH']), Path(os.environ['DOUBAO_SHORTCUT_TEST_TARGET']), 'Doubao ASR icon smoke')"
    if ($LASTEXITCODE -ne 0) {
      throw "Shortcut icon smoke creation failed"
    }
  }
  finally {
    $env:DOUBAO_SHORTCUT_TEST_PATH = $OldShortcutPath
    $env:DOUBAO_SHORTCUT_TEST_TARGET = $OldShortcutTarget
  }
  $Shell = New-Object -ComObject WScript.Shell
  $Link = $Shell.CreateShortcut($Shortcut)
  $Expected = "$TargetExe,0"
  if ($Link.IconLocation -ne $Expected) {
    throw "Shortcut does not pin the app icon. Expected '$Expected', got '$($Link.IconLocation)'"
  }
}

function Invoke-AppSelfTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--self-test", "--self-test-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Self-test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Self-test report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "Self-test report says ok=false: $ReportPath"
  }
  if ($null -eq $Report.license_config) {
    throw "Self-test report is missing license_config: $ReportPath"
  }
  return $ReportPath
}

function Invoke-TraySelfTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--tray-self-test", "--tray-self-test-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Tray self-test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Tray self-test report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "Tray self-test report says ok=false: $ReportPath"
  }
  if (-not $Report.started -or -not $Report.stopped) {
    throw "Tray self-test did not start and stop cleanly: $ReportPath"
  }
  if (-not $Report.icon_exists -or -not $Report.icon_loaded_from_file) {
    throw "Tray self-test did not load the bundled app icon: $ReportPath"
  }
  return $ReportPath
}

function Invoke-FloatLayoutTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--float-layout-test", "--float-layout-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Float layout test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Float layout report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.fits_text_sample) {
    throw "Float layout sample text does not fit: $ReportPath"
  }
  if (-not $Report.fits_screen) {
    throw "Float layout exceeds screen bounds: $ReportPath"
  }
  if (-not $Report.text_equal_input) {
    throw "Float layout report says the displayed text changed: $ReportPath"
  }
  return $ReportPath
}

function Invoke-ClipboardInsertTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--clipboard-insert-test", "--clipboard-insert-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Clipboard insert test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Clipboard insert report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "Clipboard insert report says ok=false: $ReportPath"
  }
  if (-not $Report.text_inserted -or -not $Report.clipboard_restored) {
    throw "Clipboard insert test did not prove both insertion and restore: $ReportPath"
  }
  return $ReportPath
}

function Invoke-ClipboardComplexTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--clipboard-complex-test", "--clipboard-complex-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Complex clipboard test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Complex clipboard report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "Complex clipboard report says ok=false: $ReportPath"
  }
  if (-not $Report.native_clipboard_available) {
    throw "Complex clipboard report did not use native Windows clipboard APIs: $ReportPath"
  }
  if (@($Report.cases).Count -lt 2) {
    throw "Complex clipboard report is missing image/file cases: $ReportPath"
  }
  foreach ($Case in $Report.cases) {
    if (-not $Case.text_inserted -or -not $Case.format_restored) {
      throw "Complex clipboard case did not prove insertion and format restore: $($Case.name)"
    }
  }
  return $ReportPath
}

function Invoke-StartupScriptTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  $Sandbox = Join-Path $ReportsDir "startup-script-sandbox"
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  $LocalAppData = Join-Path $Sandbox "LocalAppData"
  $AppData = Join-Path $Sandbox "AppData"
  $UserProfile = Join-Path $Sandbox "UserProfile"
  New-Item -ItemType Directory -Force -Path $LocalAppData, $AppData, $UserProfile | Out-Null

  $EnvMap = @{
    "LOCALAPPDATA" = $LocalAppData
    "APPDATA" = $AppData
    "USERPROFILE" = $UserProfile
    "DOUBAO_ASR_CONFIG_DIR" = (Join-Path $Sandbox "Config")
  }

  $ExitCode = Start-IsolatedProcess -FileName $ExePath -Arguments "--startup-script-test --startup-script-report `"$ReportPath`"" -Environment $EnvMap -TimeoutSeconds 60
  if ($ExitCode -ne 0) {
    throw "Startup script test failed for $ExePath with exit code $ExitCode"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Startup script report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok -or -not $Report.created -or -not $Report.removed) {
    throw "Startup script report says startup create/remove failed: $ReportPath"
  }
  if (-not $Report.contains_executable -or -not $Report.contains_hidden_flag) {
    throw "Startup script report did not prove executable path and --hidden flag: $ReportPath"
  }
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  return $ReportPath
}

function Invoke-LicenseNetworkTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  $Sandbox = Join-Path $ReportsDir "license-network-sandbox"
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $Sandbox | Out-Null

  $EnvMap = @{
    "DOUBAO_ASR_CONFIG_DIR" = $Sandbox
    "APPDATA" = (Join-Path $Sandbox "AppData")
    "LOCALAPPDATA" = (Join-Path $Sandbox "LocalAppData")
    "USERPROFILE" = (Join-Path $Sandbox "UserProfile")
  }

  $ExitCode = Start-IsolatedProcess -FileName $ExePath -Arguments "--license-network-test --license-network-report `"$ReportPath`"" -Environment $EnvMap -TimeoutSeconds 30
  if ($ExitCode -ne 0) {
    throw "License network test failed for $ExePath with exit code $ExitCode"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "License network report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "License network report says ok=false: $ReportPath"
  }
  if (-not $Report.ordinary_build_ok -or -not $Report.required_build_blocks -or -not $Report.cached_token_preserved) {
    throw "License network report did not prove ordinary/controlled offline behavior: $ReportPath"
  }
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  return $ReportPath
}

function Start-IsolatedProcess {
  param(
    [Parameter(Mandatory = $true)][string]$FileName,
    [Parameter(Mandatory = $true)][string]$Arguments,
    [Parameter(Mandatory = $true)][hashtable]$Environment,
    [int]$TimeoutSeconds = 60
  )

  $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $StartInfo.FileName = $FileName
  $StartInfo.Arguments = $Arguments
  $StartInfo.UseShellExecute = $false
  $StartInfo.CreateNoWindow = $true
  foreach ($Key in $Environment.Keys) {
    $StartInfo.Environment[$Key] = [string]$Environment[$Key]
  }

  $Process = [System.Diagnostics.Process]::new()
  $Process.StartInfo = $StartInfo
  if (-not $Process.Start()) {
    throw "Failed to start process: $FileName"
  }
  if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
    try {
      $Process.Kill()
    }
    catch {
    }
    throw "Timed out waiting for process: $FileName $Arguments"
  }
  return $Process.ExitCode
}

function Invoke-UninstallCleanupTest {
  param(
    [Parameter(Mandatory = $true)][string]$SetupExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $SetupExePath)) {
    throw "Missing setup executable: $SetupExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  $Sandbox = Join-Path $ReportsDir "uninstall-sandbox"
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  $LocalAppData = Join-Path $Sandbox "LocalAppData"
  $AppData = Join-Path $Sandbox "AppData"
  $UserProfile = Join-Path $Sandbox "UserProfile"
  $Desktop = Join-Path $UserProfile "Desktop"
  New-Item -ItemType Directory -Force -Path $LocalAppData, $AppData, $Desktop | Out-Null

  $EnvMap = @{
    "LOCALAPPDATA" = $LocalAppData
    "APPDATA" = $AppData
    "USERPROFILE" = $UserProfile
  }

  $InstallExit = Start-IsolatedProcess -FileName $SetupExePath -Arguments "--silent --no-run" -Environment $EnvMap -TimeoutSeconds 90
  if ($InstallExit -ne 0) {
    throw "Isolated installer failed with exit code $InstallExit"
  }

  $InstallDir = Join-Path $LocalAppData "DoubaoASRHelper"
  $InstalledExe = Join-Path $InstallDir "DoubaoASRHelper.exe"
  $UninstallCmd = Join-Path $InstallDir "uninstall.cmd"
  $StartMenuDir = Join-Path $AppData "Microsoft\Windows\Start Menu\Programs\Doubao ASR Helper"
  $DesktopShortcut = Join-Path $Desktop "Doubao ASR Helper.lnk"
  $StartupBat = Join-Path $AppData "Microsoft\Windows\Start Menu\Programs\Startup\doubaoime-asr.bat"
  New-Item -ItemType Directory -Force -Path (Split-Path $StartupBat -Parent) | Out-Null
  Set-Content -LiteralPath $StartupBat -Value "@echo off`r`nrem uninstall smoke`r`n" -Encoding UTF8

  $InstallChecks = @{
    installed_exe = Test-Path $InstalledExe
    uninstall_cmd = Test-Path $UninstallCmd
    start_menu_app = Test-Path (Join-Path $StartMenuDir "Doubao ASR Helper.lnk")
    start_menu_help = Test-Path (Join-Path $StartMenuDir "Help.lnk")
    start_menu_uninstall = Test-Path (Join-Path $StartMenuDir "Uninstall Doubao ASR Helper.lnk")
    desktop_shortcut = Test-Path $DesktopShortcut
    startup_bat_seeded = Test-Path $StartupBat
  }
  if ($InstallChecks.Values -contains $false) {
    throw "Isolated install did not create expected files"
  }

  $UninstallExit = Start-IsolatedProcess -FileName "cmd.exe" -Arguments "/c `"$UninstallCmd`"" -Environment $EnvMap -TimeoutSeconds 90

  $CleanupDeadline = (Get-Date).AddSeconds(15)
  while ((Get-Date) -lt $CleanupDeadline -and (Test-Path $InstallDir)) {
    Start-Sleep -Milliseconds 250
  }

  $CleanupChecks = @{
    install_dir_removed = -not (Test-Path $InstallDir)
    start_menu_dir_removed = -not (Test-Path $StartMenuDir)
    desktop_shortcut_removed = -not (Test-Path $DesktopShortcut)
    startup_bat_removed = -not (Test-Path $StartupBat)
  }
  if ($CleanupChecks.Values -contains $false) {
    throw "Isolated uninstall did not clean expected files"
  }

  $Report = [ordered]@{
    ok = $true
    test_id = "T16"
    name = "isolated installer shortcut and uninstall cleanup"
    sandbox = $Sandbox
    install_exit_code = $InstallExit
    uninstall_exit_code = $UninstallExit
    install_checks = $InstallChecks
    cleanup_checks = $CleanupChecks
  }
  $Report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
  Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
  return $ReportPath
}

function Wait-AppWindow {
  param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$ExePath,
    [int]$TimeoutSeconds = 15
  )

  $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $Deadline) {
    $Candidates = @()
    $StartedProcess = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($StartedProcess) {
      $Candidates += $StartedProcess
    }
    $Candidates += Get-Process DoubaoASRHelper -ErrorAction SilentlyContinue |
      Where-Object { $_.Path -eq $ExePath }

    foreach ($Candidate in $Candidates) {
      $WindowHandle = [DoubaoWin32Capture]::FindWindowForProcess($Candidate.Id, $MainWindowTitle, 300, 250)
      if ($WindowHandle -ne [IntPtr]::Zero) {
        return [pscustomobject]@{
          Process = $Candidate
          WindowHandle = $WindowHandle
        }
      }
    }
    Start-Sleep -Milliseconds 250
  }
  throw "Timed out waiting for app window from $ExePath"
}

function Save-AppWindowScreenshot {
  param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName,
    [int]$StabilizeMilliseconds = 3000,
    [int]$WindowWidth = 820,
    [int]$WindowHeight = 680,
    [switch]$PreserveWindowSize,
    [switch]$Background
  )

  $Window = Wait-AppWindow -ProcessId $ProcessId -ExePath $ExePath
  $InitialRect = New-Object RECT
  [DoubaoWin32Capture]::GetWindowRect($Window.WindowHandle, [ref]$InitialRect) | Out-Null
  if ($PreserveWindowSize) {
    $WindowWidth = $InitialRect.Right - $InitialRect.Left
    $WindowHeight = $InitialRect.Bottom - $InitialRect.Top
  }

  if ($Background) {
    if (-not [DoubaoWin32Capture]::SetWindowPos($Window.WindowHandle, $HwndBottom, 40, 80, $WindowWidth, $WindowHeight, ($SwpShowWindow -bor $SwpNoActivate))) {
      throw "Could not position app window in background for screenshot"
    }
  }
  else {
    if (-not [DoubaoWin32Capture]::SetWindowPos($Window.WindowHandle, $HwndTopMost, 40, 80, $WindowWidth, $WindowHeight, $SwpShowWindow)) {
      throw "Could not make app window topmost for screenshot"
    }
    if (-not [DoubaoWin32Capture]::MoveWindow($Window.WindowHandle, 40, 80, $WindowWidth, $WindowHeight, $true)) {
      throw "Could not move app window for screenshot"
    }
    [DoubaoWin32Capture]::SetForegroundWindow($Window.WindowHandle) | Out-Null
  }
  Start-Sleep -Milliseconds $StabilizeMilliseconds

  $Rect = New-Object RECT
  [DoubaoWin32Capture]::GetWindowRect($Window.WindowHandle, [ref]$Rect) | Out-Null
  $Width = $Rect.Right - $Rect.Left
  $Height = $Rect.Bottom - $Rect.Top
  $MinExpectedWidth = [Math]::Max([int]($WindowWidth * 0.7), 360)
  $MinExpectedHeight = [Math]::Max([int]($WindowHeight * 0.7), 280)
  if ($Width -lt $MinExpectedWidth -or $Height -lt $MinExpectedHeight) {
    throw "Visible app window is unexpectedly small: ${Width}x${Height}"
  }

  $ScreenshotPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ScreenshotPath -Force -ErrorAction SilentlyContinue
  $Bitmap = New-Object System.Drawing.Bitmap $Width, $Height
  $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
  try {
    $Rendered = $false
    $Hdc = $Graphics.GetHdc()
    try {
      $Rendered = [DoubaoWin32Capture]::PrintWindow($Window.WindowHandle, $Hdc, [uint32]2)
    }
    finally {
      $Graphics.ReleaseHdc($Hdc)
    }
    if (-not $Rendered) {
      $Graphics.CopyFromScreen($Rect.Left, $Rect.Top, 0, 0, $Bitmap.Size)
    }
    $Bitmap.Save($ScreenshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
  }
  finally {
    $Graphics.Dispose()
    $Bitmap.Dispose()
    $RestoreTarget = if ($Background) { $HwndBottom } else { $HwndNoTopMost }
    $RestoreFlags = if ($Background) { $SwpShowWindow -bor $SwpNoActivate } else { $SwpShowWindow }
    [DoubaoWin32Capture]::SetWindowPos($Window.WindowHandle, $RestoreTarget, $Rect.Left, $Rect.Top, $Width, $Height, $RestoreFlags) | Out-Null
  }
  if (-not (Test-Path $ScreenshotPath)) {
    throw "UI screenshot was not written: $ScreenshotPath"
  }
  Trim-BlackScreenshotBorder -ScreenshotPath $ScreenshotPath | Out-Null
  Assert-UiScreenshotLooksVisible -ScreenshotPath $ScreenshotPath
  return $ScreenshotPath
}

function Trim-BlackScreenshotBorder {
  param([Parameter(Mandatory = $true)][string]$ScreenshotPath)

  $Bitmap = [System.Drawing.Bitmap]::FromFile($ScreenshotPath)
  $Trimmed = $null
  try {
    $MinX = $Bitmap.Width
    $MinY = $Bitmap.Height
    $MaxX = -1
    $MaxY = -1
    for ($Y = 0; $Y -lt $Bitmap.Height; $Y++) {
      for ($X = 0; $X -lt $Bitmap.Width; $X++) {
        $Color = $Bitmap.GetPixel($X, $Y)
        if (($Color.R + $Color.G + $Color.B) -gt 24) {
          if ($X -lt $MinX) { $MinX = $X }
          if ($Y -lt $MinY) { $MinY = $Y }
          if ($X -gt $MaxX) { $MaxX = $X }
          if ($Y -gt $MaxY) { $MaxY = $Y }
        }
      }
    }
    if ($MaxX -lt $MinX -or $MaxY -lt $MinY) {
      return
    }
    $TrimWidth = $MaxX - $MinX + 1
    $TrimHeight = $MaxY - $MinY + 1
    if ($TrimWidth -eq $Bitmap.Width -and $TrimHeight -eq $Bitmap.Height) {
      return
    }
    if ($TrimWidth -lt 240 -or $TrimHeight -lt 180) {
      return
    }
    $Rect = New-Object System.Drawing.Rectangle $MinX, $MinY, $TrimWidth, $TrimHeight
    $Trimmed = $Bitmap.Clone($Rect, $Bitmap.PixelFormat)
  }
  finally {
    $Bitmap.Dispose()
  }

  if ($null -ne $Trimmed) {
    try {
      $TempPath = "$ScreenshotPath.tmp.png"
      $Trimmed.Save($TempPath, [System.Drawing.Imaging.ImageFormat]::Png)
      Move-Item -LiteralPath $TempPath -Destination $ScreenshotPath -Force
    }
    finally {
      $Trimmed.Dispose()
    }
  }
}

function Assert-UiScreenshotLooksVisible {
  param([Parameter(Mandatory = $true)][string]$ScreenshotPath)

  $Bitmap = [System.Drawing.Bitmap]::FromFile($ScreenshotPath)
  try {
    $Total = 0.0
    $Count = 0
    $StepX = [Math]::Max([int]($Bitmap.Width / 40), 1)
    $StepY = [Math]::Max([int]($Bitmap.Height / 40), 1)
    for ($Y = 0; $Y -lt $Bitmap.Height; $Y += $StepY) {
      for ($X = 0; $X -lt $Bitmap.Width; $X += $StepX) {
        $Color = $Bitmap.GetPixel($X, $Y)
        $Total += (0.2126 * $Color.R) + (0.7152 * $Color.G) + (0.0722 * $Color.B)
        $Count += 1
      }
    }
    $AverageLuma = $Total / [Math]::Max($Count, 1)
    if ($AverageLuma -lt 150) {
      throw "UI screenshot looks too dark to be the light Tk settings window (average luma $([Math]::Round($AverageLuma, 2))): $ScreenshotPath"
    }
  }
  finally {
    $Bitmap.Dispose()
  }
}

function Wait-UiLayoutReport {
  param(
    [Parameter(Mandatory = $true)][string]$ReportPath,
    [int]$TimeoutSeconds = 10
  )

  $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $Deadline) {
    if (Test-Path $ReportPath) {
      try {
        return Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
      }
      catch {
        Start-Sleep -Milliseconds 200
      }
    }
    Start-Sleep -Milliseconds 250
  }
  throw "UI layout report was not written: $ReportPath"
}

function Assert-UiLayoutFits {
  param([Parameter(Mandatory = $true)][string]$ReportPath)

  $Layout = Wait-UiLayoutReport -ReportPath $ReportPath
  if (-not $Layout.content.fits_horizontally -or -not $Layout.content.fits_vertically) {
    throw "UI layout does not fit in one page: $ReportPath"
  }
  $RootWidth = [int]$Layout.root.width
  $RootHeight = [int]$Layout.root.height
  $Overflow = @($Layout.widgets | Where-Object {
      [int]$_.right -gt ($RootWidth + 2) -or [int]$_.bottom -gt ($RootHeight + 2)
    })
  if ($Overflow.Count -gt 0) {
    $Names = ($Overflow | Select-Object -ExpandProperty name) -join ", "
    throw "UI widgets overflow the visible window: $Names"
  }
  foreach ($Name in @("status", "checks", "actions", "mode-0", "mode-1", "mode-2", "option-protect_clipboard", "option-startup")) {
    if (-not ($Layout.widgets | Where-Object { $_.name -eq $Name })) {
      throw "UI layout report missing required widget: $Name"
    }
  }
  $OptionToggles = @($Layout.widgets | Where-Object { $_.name -like "option-*" })
  $SmallOptionToggles = @($OptionToggles | Where-Object { [int]$_.height -lt 28 -or [int]$_.width -lt 86 })
  if ($SmallOptionToggles.Count -gt 0) {
    throw "Settings option toggles are too small: $($SmallOptionToggles.name -join ', ')"
  }
  $Title = $Layout.widgets | Where-Object { $_.name -eq "title" } | Select-Object -First 1
  $EntriesForType = @($Layout.widgets | Where-Object { $_.name -match '^setting-\d+-entry$' })
  if ($Title -and $EntriesForType.Count -gt 0) {
    $EntryHeights = @($EntriesForType | ForEach-Object { [int]$_.height })
    $AverageEntryHeight = ($EntryHeights | Measure-Object -Average).Average
    if ([int]$Title.height -gt [Math]::Ceiling($AverageEntryHeight * 1.35)) {
      throw "Title typography is too large compared with setting inputs: $ReportPath"
    }
  }
  $LabelsForType = @($Layout.widgets | Where-Object { $_.name -match '^setting-\d+-label$' })
  if ($LabelsForType.Count -gt 1) {
    $LabelHeights = @($LabelsForType | ForEach-Object { [int]$_.height })
    $LabelHeightSpread = ($LabelHeights | Measure-Object -Maximum).Maximum - ($LabelHeights | Measure-Object -Minimum).Minimum
    if ($LabelHeightSpread -gt 8) {
      throw "Setting label typography is inconsistent: $ReportPath"
    }
  }
  $DescriptionsForType = @($Layout.widgets | Where-Object { $_.name -match '^setting-\d+-desc$' })
  if ($DescriptionsForType.Count -gt 1) {
    $DescriptionHeights = @($DescriptionsForType | ForEach-Object { [int]$_.height })
    $DescriptionHeightSpread = ($DescriptionHeights | Measure-Object -Maximum).Maximum - ($DescriptionHeights | Measure-Object -Minimum).Minimum
    if ($DescriptionHeightSpread -gt 8) {
      throw "Setting descriptions wrap inconsistently across rows: $ReportPath"
    }
    foreach ($Description in $DescriptionsForType) {
      $Index = [regex]::Match([string]$Description.name, '^setting-(\d+)-desc$').Groups[1].Value
      $Label = $LabelsForType | Where-Object { $_.name -eq "setting-$Index-label" } | Select-Object -First 1
      if ($Label -and [Math]::Abs([int]$Description.x - [int]$Label.x) -gt 4) {
        throw "Setting description is not aligned under its label: $($Description.name)"
      }
    }
  }
  $RequiredEntries = @(
    "hold_key",
    "toggle_key",
    "hold_send_key",
    "cancel_key",
    "doubao_hotkey"
  )
  foreach ($Key in $RequiredEntries) {
    if (-not ($Layout.widgets | Where-Object { $_.name -eq "setting-$Key-entry" })) {
      throw "UI layout report missing setting entry: $Key"
    }
  }
  foreach ($Name in @("setting-insert_delay_ms-scale", "setting-insert_delay_ms-value")) {
    if (-not ($Layout.widgets | Where-Object { $_.name -eq $Name })) {
      throw "UI layout report missing insert delay control: $Name"
    }
  }
  $AlignedButtons = @($Layout.widgets | Where-Object { $_.name -match '^setting-(hold_key|toggle_key|hold_send_key|cancel_key)-button$' })
  if ($AlignedButtons.Count -ge 2) {
    $ButtonXs = @($AlignedButtons | ForEach-Object { [int]$_.x })
    $ButtonSpread = ($ButtonXs | Measure-Object -Maximum).Maximum - ($ButtonXs | Measure-Object -Minimum).Minimum
    if ($ButtonSpread -gt 8) {
      throw "Setting record/select buttons are not vertically aligned: $($AlignedButtons.name -join ', ')"
    }
  }
  $AlignedEntries = @($Layout.widgets | Where-Object { $_.name -match '^setting-(hold_key|toggle_key|hold_send_key|cancel_key)-entry$' })
  if ($AlignedEntries.Count -ge 2) {
    $EntryXs = @($AlignedEntries | ForEach-Object { [int]$_.x })
    $EntrySpread = ($EntryXs | Measure-Object -Maximum).Maximum - ($EntryXs | Measure-Object -Minimum).Minimum
    if ($EntrySpread -gt 8) {
      throw "Setting text entries are not vertically aligned: $($AlignedEntries.name -join ', ')"
    }
  }
  foreach ($DelayName in @("insert_delay_ms", "clipboard_restore_delay_ms", "auto_send_delay_ms")) {
    $Delay = $Layout.delays.$DelayName
    if ($null -eq $Delay) {
      throw "UI layout report missing delay value: $DelayName"
    }
    if ([int]$Delay.step -ne 50 -or ([int]$Delay.value % 50) -ne 0) {
      throw "Delay slider does not snap to 50ms steps: $DelayName=$($Delay.value), step=$($Delay.step)"
    }
  }
  foreach ($HotkeyName in @("hold_key", "toggle_key", "hold_send_key", "cancel_key", "doubao_hotkey")) {
    $Hotkey = [string]$Layout.hotkeys.$HotkeyName
    if ([string]::IsNullOrWhiteSpace($Hotkey)) {
      throw "UI layout report missing hotkey value: $HotkeyName"
    }
    if ($Hotkey -match '\b[lr](ctrl|win|alt|shift)\b' -or $Hotkey -match 'xbutton') {
      throw "Hotkey is exposing internal key names instead of user-facing labels: $HotkeyName=$Hotkey"
    }
  }
  $ExpectedActionButtons = 6
  $ActionButtons = @($Layout.widgets | Where-Object { $_.name -like "action-*" })
  if ($ActionButtons.Count -ne $ExpectedActionButtons) {
    throw "UI layout report expected $ExpectedActionButtons action buttons, found $($ActionButtons.Count)"
  }
  for ($Index = 0; $Index -lt $ExpectedActionButtons; $Index++) {
    if (-not ($Layout.widgets | Where-Object { $_.name -eq "action-$Index" })) {
      throw "UI layout report missing action button $Index"
    }
  }
  return $ReportPath
}

function Assert-UiVisualSizeAtScale {
  param([Parameter(Mandatory = $true)][string]$ReportPath)

  $Layout = Wait-UiLayoutReport -ReportPath $ReportPath
  $Scale = [double]$Layout.display.ui_scale_factor
  if ($Scale -lt 1.9) {
    return $ReportPath
  }

  $Title = $Layout.widgets | Where-Object { $_.name -eq "title" } | Select-Object -First 1
  if ($Title -and [int]$Title.height -lt 30) {
    throw "High-DPI title is too small in layout report: $ReportPath"
  }
  $Entries = @($Layout.widgets | Where-Object { $_.name -like "setting-*-entry" })
  $SmallEntries = @($Entries | Where-Object { [int]$_.height -lt 38 })
  if ($SmallEntries.Count -gt 0) {
    throw "High-DPI entry widgets are too small: $($SmallEntries.name -join ', ')"
  }
  $RecordButtons = @($Layout.widgets | Where-Object { $_.name -like "setting-*-button" })
  $SmallRecordButtons = @($RecordButtons | Where-Object { [int]$_.height -lt 40 })
  if ($SmallRecordButtons.Count -gt 0) {
    throw "High-DPI setting buttons are too small: $($SmallRecordButtons.name -join ', ')"
  }
  $ActionButtons = @($Layout.widgets | Where-Object { $_.name -like "action-*" })
  $SmallActions = @($ActionButtons | Where-Object { [int]$_.height -lt 44 -or [int]$_.width -lt 110 })
  if ($SmallActions.Count -gt 0) {
    throw "High-DPI action buttons are too small: $($SmallActions.name -join ', ')"
  }
  $OptionToggles = @($Layout.widgets | Where-Object { $_.name -like "option-*" })
  $SmallOptionToggles = @($OptionToggles | Where-Object { [int]$_.height -lt 38 -or [int]$_.width -lt 120 })
  if ($SmallOptionToggles.Count -gt 0) {
    throw "High-DPI option toggles are too small: $($SmallOptionToggles.name -join ', ')"
  }
  $Scales = @($Layout.widgets | Where-Object { $_.name -like "setting-*-scale" })
  $SmallScales = @($Scales | Where-Object { [int]$_.height -lt 18 })
  if ($SmallScales.Count -gt 0) {
    throw "High-DPI sliders are too small: $($SmallScales.name -join ', ')"
  }
  return $ReportPath
}

function Assert-DefaultScaleWindowComfortable {
  param([Parameter(Mandatory = $true)][string]$ReportPath)

  $Layout = Wait-UiLayoutReport -ReportPath $ReportPath
  $Scale = [double]$Layout.display.ui_scale_factor
  if ($Scale -lt 1.2) {
    return $ReportPath
  }
  if (-not ($Layout.display.PSObject.Properties.Name -contains "default_window_scaled") -or -not $Layout.display.default_window_scaled) {
    throw "Default window scaling was not applied: $ReportPath"
  }
  $ScreenWidth = [int]$Layout.display.screen_width
  $ScreenHeight = [int]$Layout.display.screen_height
  $WindowScale = [Math]::Min([Math]::Max($Scale, 1.0), 2.5)
  $ExpectedWidth = [Math]::Min([int][Math]::Round(900 * $WindowScale), [int]($ScreenWidth * 0.9))
  $ExpectedHeight = [Math]::Min([int][Math]::Round(680 * $WindowScale), [int]($ScreenHeight * 0.88))
  $RootWidth = [int]$Layout.root.width
  $RootHeight = [int]$Layout.root.height
  if ($RootWidth -lt ($ExpectedWidth - 32) -or $RootHeight -lt ($ExpectedHeight - 32)) {
    throw "Default high-DPI window is too small: got ${RootWidth}x${RootHeight}, expected about ${ExpectedWidth}x${ExpectedHeight}"
  }
  return $ReportPath
}

function Assert-CloseToTrayKeepsAlive {
  param([Parameter(Mandatory = $true)][string]$ExePath)

  $App = Start-Process $ExePath -ArgumentList "--background" -PassThru
  try {
    $Window = Wait-AppWindow -ProcessId $App.Id -ExePath $ExePath
    [DoubaoWin32Capture]::PostMessage($Window.WindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    Start-Sleep -Seconds 2
    $StillRunning = Get-Process -Id $Window.Process.Id -ErrorAction SilentlyContinue
    if (-not $StillRunning) {
      throw "App exited after WM_CLOSE instead of hiding to tray"
    }
    $VisibleWindow = [DoubaoWin32Capture]::FindWindowForProcess($Window.Process.Id, $MainWindowTitle, 300, 250)
    if ($VisibleWindow -ne [IntPtr]::Zero) {
      throw "Main window is still visible after WM_CLOSE"
    }
    return [pscustomobject]@{
      ProcessId = $Window.Process.Id
      HiddenToTray = $true
    }
  }
  finally {
    Stop-Process -Id $App.Id -Force -ErrorAction SilentlyContinue
    Stop-AppFromPath -ExePath $ExePath
  }
}

function Assert-SingleInstanceGuard {
  param(
    [Parameter(Mandatory = $true)][string]$PrimaryExePath,
    [string]$SecondaryExePath = $PrimaryExePath
  )

  Stop-AllDoubaoAppInstances
  $First = Start-Process $PrimaryExePath -ArgumentList "--hidden" -PassThru
  try {
    Start-Sleep -Seconds 5
    if (-not (Get-Process -Id $First.Id -ErrorAction SilentlyContinue)) {
      throw "Primary app exited before the single-instance check could run"
    }
    $BeforeDuplicate = @(Get-CimInstance Win32_Process |
      Where-Object { $_.ExecutablePath -like "*DoubaoASRHelper*.exe" })
    if ($BeforeDuplicate.Count -lt 1) {
      throw "Primary app did not leave any Doubao ASR process running"
    }

    $Second = Start-Process $SecondaryExePath -ArgumentList "--hidden" -PassThru
    if (-not $Second.WaitForExit(8000)) {
      Stop-Process -Id $Second.Id -Force -ErrorAction SilentlyContinue
      throw "Second app instance did not exit after detecting the first instance"
    }
    $Second.Refresh()
    if ($Second.ExitCode -ne 0) {
      throw "Second app instance exited with code $($Second.ExitCode)"
    }

    Start-Sleep -Seconds 1
    $Running = @(Get-CimInstance Win32_Process |
      Where-Object { $_.ExecutablePath -like "*DoubaoASRHelper*.exe" })
    if ($Running.Count -ne $BeforeDuplicate.Count) {
      $Paths = ($Running | Select-Object -ExpandProperty ExecutablePath) -join ", "
      throw "Duplicate launch changed the Doubao ASR process count from $($BeforeDuplicate.Count) to $($Running.Count): $Paths"
    }
    return [pscustomobject]@{
      PrimaryProcessId = $First.Id
      DuplicateExited = $true
      RunningProcessCount = $Running.Count
    }
  }
  finally {
    Stop-Process -Id $First.Id -Force -ErrorAction SilentlyContinue
    Stop-AllDoubaoAppInstances
  }
}

function Stop-AppFromPath {
  param([Parameter(Mandatory = $true)][string]$ExePath)

  Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -eq $ExePath } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-AllDoubaoAppInstances {
  Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -like "*DoubaoASRHelper*.exe" } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Remove-WithRetry {
  param([Parameter(Mandatory = $true)][string]$Path)

  for ($Index = 0; $Index -lt 12; $Index++) {
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $Path)) {
      return
    }
  }
  throw "Could not remove path after retries: $Path"
}

Invoke-AppSelfTest -ExePath $DistExe -ReportName "dist-self-test.json" | Out-Host
Invoke-AppSelfTest -ExePath $PortableExe -ReportName "portable-self-test.json" | Out-Host
Assert-CustomAppIcon -ExePath $DistExe | Out-Host
Assert-CustomAppIcon -ExePath $SetupExe | Out-Host
Assert-CustomAppIcon -ExePath $PortableExe | Out-Host
Invoke-TraySelfTest -ExePath $DistExe -ReportName "dist-tray-self-test.json" | Out-Host
Invoke-TraySelfTest -ExePath $PortableExe -ReportName "portable-tray-self-test.json" | Out-Host

$OldRequireActivation = $env:DOUBAO_ASR_REQUIRE_ACTIVATION
$OldLicenseUrl = $env:DOUBAO_ASR_LICENSE_URL
$OldConfigDir = $env:DOUBAO_ASR_CONFIG_DIR
$ActivationConfigDir = Join-Path $ReportsDir "activation-self-test-config"
Remove-Item -LiteralPath $ActivationConfigDir -Recurse -Force -ErrorAction SilentlyContinue
try {
  $env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
  $env:DOUBAO_ASR_LICENSE_URL = "http://127.0.0.1:9"
  $env:DOUBAO_ASR_CONFIG_DIR = $ActivationConfigDir
  $ActivationReportPath = Invoke-AppSelfTest -ExePath $DistExe -ReportName "activation-required-self-test.json"
  $ActivationReport = Get-Content -Raw -Encoding UTF8 -LiteralPath $ActivationReportPath | ConvertFrom-Json
  if (-not $ActivationReport.license_config.require_activation) {
    throw "Activation-required self-test did not enable activation mode"
  }
}
finally {
  $env:DOUBAO_ASR_REQUIRE_ACTIVATION = $OldRequireActivation
  $env:DOUBAO_ASR_LICENSE_URL = $OldLicenseUrl
  $env:DOUBAO_ASR_CONFIG_DIR = $OldConfigDir
}

if (-not (Test-Path $ReleaseZip)) {
  throw "Missing release zip: $ReleaseZip"
}
if (-not (Test-Path $PortableZip)) {
  throw "Missing portable zip: $PortableZip"
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::OpenRead($ReleaseZip)
try {
  $Expected = @("DoubaoASRHelperSetup.exe", "DoubaoASRHelper-portable.exe", "README-Windows.txt", "HELP.md")
  foreach ($Name in $Expected) {
    if (-not ($Zip.Entries | Where-Object { $_.FullName -eq $Name -and $_.Length -gt 0 })) {
      throw "Release zip missing required entry: $Name"
    }
  }
}
finally {
  $Zip.Dispose()
}

$Zip = [IO.Compression.ZipFile]::OpenRead($PortableZip)
try {
  $Expected = @("DoubaoASRHelper-portable.exe", "README-Portable.txt", "HELP.md")
  foreach ($Name in $Expected) {
    if (-not ($Zip.Entries | Where-Object { $_.FullName -eq $Name -and $_.Length -gt 0 })) {
      throw "Portable zip missing required entry: $Name"
    }
  }
}
finally {
  $Zip.Dispose()
}

Invoke-UninstallCleanupTest -SetupExePath $SetupExe -ReportName "isolated-uninstall-cleanup-test.json" | Out-Host

$TempRoot = (Resolve-Path $env:TEMP).Path
$InstallTarget = Join-Path $TempRoot "DoubaoASRHelperExeTest"
if (-not $InstallTarget.StartsWith($TempRoot)) {
  throw "Unsafe temp target: $InstallTarget"
}
Remove-Item -LiteralPath $InstallTarget -Recurse -Force -ErrorAction SilentlyContinue

$Install = Start-Process $SetupExe -ArgumentList @("--silent", "--no-shortcuts", "--no-run", "--target", $InstallTarget) -Wait -PassThru
if ($Install.ExitCode -ne 0) {
  throw "Installer failed with exit code $($Install.ExitCode)"
}

$InstalledExe = Join-Path $InstallTarget "DoubaoASRHelper.exe"
Invoke-AppSelfTest -ExePath $InstalledExe -ReportName "installed-self-test.json" | Out-Host
Assert-CustomAppIcon -ExePath $InstalledExe | Out-Host
Assert-ShortcutUsesAppIcon -TargetExe $InstalledExe | Out-Host
Invoke-TraySelfTest -ExePath $InstalledExe -ReportName "installed-tray-self-test.json" | Out-Host
Invoke-FloatLayoutTest -ExePath $InstalledExe -ReportName "installed-float-layout-long-text.json" | Out-Host
Invoke-ClipboardInsertTest -ExePath $InstalledExe -ReportName "installed-clipboard-insert-test.json" | Out-Host
Invoke-ClipboardComplexTest -ExePath $InstalledExe -ReportName "installed-clipboard-complex-test.json" | Out-Host
Invoke-StartupScriptTest -ExePath $InstalledExe -ReportName "installed-startup-script-test.json" | Out-Host
Invoke-LicenseNetworkTest -ExePath $InstalledExe -ReportName "installed-license-network-test.json" | Out-Host
Assert-SingleInstanceGuard -PrimaryExePath $InstalledExe -SecondaryExePath $PortableExe | Out-Host
Assert-CloseToTrayKeepsAlive -ExePath $InstalledExe | Out-Host

$VisibleLayoutReport = Join-Path $ReportsDir "installed-ui-smoke-layout.json"
Remove-Item -LiteralPath $VisibleLayoutReport -Force -ErrorAction SilentlyContinue
$VisibleApp = Start-Process $InstalledExe -ArgumentList @("--background", "--ui-layout-report", $VisibleLayoutReport, "--ui-window-size", "820x680") -PassThru
try {
  Save-AppWindowScreenshot -ProcessId $VisibleApp.Id -ExePath $InstalledExe -ReportName "installed-ui-smoke.png" -PreserveWindowSize -Background | Out-Host
  Assert-UiLayoutFits -ReportPath $VisibleLayoutReport | Out-Host
  Assert-UiVisualSizeAtScale -ReportPath $VisibleLayoutReport | Out-Host
}
finally {
  Stop-Process -Id $VisibleApp.Id -Force -ErrorAction SilentlyContinue
  Stop-AppFromPath -ExePath $InstalledExe
}

$NarrowLayoutReport = Join-Path $ReportsDir "installed-ui-smoke-narrow-layout.json"
Remove-Item -LiteralPath $NarrowLayoutReport -Force -ErrorAction SilentlyContinue
$NarrowApp = Start-Process $InstalledExe -ArgumentList @("--background", "--ui-layout-report", $NarrowLayoutReport, "--ui-window-size", "760x520") -PassThru
try {
  Save-AppWindowScreenshot -ProcessId $NarrowApp.Id -ExePath $InstalledExe -ReportName "installed-ui-smoke-narrow.png" -PreserveWindowSize -Background | Out-Host
  Assert-UiLayoutFits -ReportPath $NarrowLayoutReport | Out-Host
  Assert-UiVisualSizeAtScale -ReportPath $NarrowLayoutReport | Out-Host
}
finally {
  Stop-Process -Id $NarrowApp.Id -Force -ErrorAction SilentlyContinue
  Stop-AppFromPath -ExePath $InstalledExe
}

$MinimumLayoutReport = Join-Path $ReportsDir "installed-ui-smoke-minimum-layout.json"
Remove-Item -LiteralPath $MinimumLayoutReport -Force -ErrorAction SilentlyContinue
$MinimumApp = Start-Process $InstalledExe -ArgumentList @("--background", "--ui-layout-report", $MinimumLayoutReport, "--ui-window-size", "560x420") -PassThru
try {
  Save-AppWindowScreenshot -ProcessId $MinimumApp.Id -ExePath $InstalledExe -ReportName "installed-ui-smoke-minimum.png" -PreserveWindowSize -Background | Out-Host
  Assert-UiLayoutFits -ReportPath $MinimumLayoutReport | Out-Host
  Assert-UiVisualSizeAtScale -ReportPath $MinimumLayoutReport | Out-Host
}
finally {
  Stop-Process -Id $MinimumApp.Id -Force -ErrorAction SilentlyContinue
  Stop-AppFromPath -ExePath $InstalledExe
}

$ScaleScenarios = @(
  @{ Name = "installed-ui-smoke-scale150-minimum-layout.json"; Size = "560x420"; Scale = "1.5" },
  @{ Name = "installed-ui-smoke-scale200-narrow-layout.json"; Size = "760x520"; Scale = "2.0" },
  @{ Name = "installed-ui-smoke-scale200-minimum-layout.json"; Size = "560x420"; Scale = "2.0" }
)
foreach ($Scenario in $ScaleScenarios) {
  $ScaleReport = Join-Path $ReportsDir $Scenario.Name
  Remove-Item -LiteralPath $ScaleReport -Force -ErrorAction SilentlyContinue
  $ScaleApp = Start-Process $InstalledExe -ArgumentList @(
    "--background",
    "--ui-layout-report", $ScaleReport,
    "--ui-window-size", $Scenario.Size,
    "--ui-scale-factor", $Scenario.Scale
  ) -PassThru
  try {
    Assert-UiLayoutFits -ReportPath $ScaleReport | Out-Host
    Assert-UiVisualSizeAtScale -ReportPath $ScaleReport | Out-Host
    $ScaleLayout = Wait-UiLayoutReport -ReportPath $ScaleReport
    $ActualScale = [double]$ScaleLayout.display.ui_scale_factor
    $ExpectedScale = [double]$Scenario.Scale
    if ([Math]::Abs($ActualScale - $ExpectedScale) -gt 0.05) {
      throw "UI scale report expected $ExpectedScale, got $ActualScale"
    }
  }
  finally {
    Stop-Process -Id $ScaleApp.Id -Force -ErrorAction SilentlyContinue
    Stop-AppFromPath -ExePath $InstalledExe
  }
}

$DefaultScaleReport = Join-Path $ReportsDir "installed-ui-smoke-scale200-default-layout.json"
Remove-Item -LiteralPath $DefaultScaleReport -Force -ErrorAction SilentlyContinue
$DefaultScaleApp = Start-Process $InstalledExe -ArgumentList @(
  "--background",
  "--ui-layout-report", $DefaultScaleReport,
  "--ui-scale-factor", "2.0"
) -PassThru
try {
  Save-AppWindowScreenshot -ProcessId $DefaultScaleApp.Id -ExePath $InstalledExe -ReportName "installed-ui-smoke-scale200-default.png" -PreserveWindowSize -Background | Out-Host
  Assert-UiLayoutFits -ReportPath $DefaultScaleReport | Out-Host
  Assert-UiVisualSizeAtScale -ReportPath $DefaultScaleReport | Out-Host
  Assert-DefaultScaleWindowComfortable -ReportPath $DefaultScaleReport | Out-Host
}
finally {
  Stop-Process -Id $DefaultScaleApp.Id -Force -ErrorAction SilentlyContinue
  Stop-AppFromPath -ExePath $InstalledExe
}

$App = Start-Process $InstalledExe -ArgumentList "--hidden" -PassThru
Start-Sleep -Seconds 5
if (-not (Get-Process -Id $App.Id -ErrorAction SilentlyContinue)) {
  throw "Installed app exited during launch smoke test"
}
Stop-Process -Id $App.Id -Force -ErrorAction SilentlyContinue
Stop-AppFromPath -ExePath $InstalledExe
Remove-WithRetry -Path $InstallTarget

Write-Host "Desktop EXE tests passed."
