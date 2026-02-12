Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression.FileSystem

# C# Bridge
$code = @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

[ComVisible(true)]
public class InstallerBridge
{
    public Action<string> OnStartInstall;
    public Action OnClose;

    public string SelectFolder()
    {
        FolderBrowserDialog fbd = new FolderBrowserDialog();
        fbd.Description = "Select Installation Directory";
        if (fbd.ShowDialog() == DialogResult.OK) return fbd.SelectedPath;
        return "";
    }

    public void StartInstall(string path)
    {
        if (OnStartInstall != null) OnStartInstall(path);
    }

    public void CloseApp()
    {
        if (OnClose != null) OnClose();
    }
}
"@
Add-Type -TypeDefinition $code -ReferencedAssemblies System.Windows.Forms

# Shared Data
$syncHash = [hashtable]::Synchronized(@{ 
    Percent = 0; Status = "Ready"; Step = 0; IsRunning = $false; IsComplete = $false; Error = $null
})

# Setup UI
$form = New-Object System.Windows.Forms.Form
$form.Text = "PyWarp Installer"
$form.Width = 750; $form.Height = 500
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$iconPath = Join-Path $PSScriptRoot "assets\logo.ico"
if (Test-Path $iconPath) { try { $form.Icon = New-Object System.Drawing.Icon($iconPath) } catch {} }

$browser = New-Object System.Windows.Forms.WebBrowser
$browser.Dock = "Fill"
$browser.ScrollBarsEnabled = $false
$browser.ScriptErrorsSuppressed = $true
$browser.IsWebBrowserContextMenuEnabled = $false

$htmlPath = Join-Path $PSScriptRoot "index.html"
$browser.Navigate((New-Object System.Uri($htmlPath)))
$form.Controls.Add($browser)

$bridge = New-Object InstallerBridge
$browser.ObjectForScripting = $bridge

function Call-JS {
    param($funcName, $arguments)
    if ($browser.Document -ne $null) {
        $browser.Document.InvokeScript($funcName, [Object[]]$arguments)
    }
}

# Install Logic
$installScriptBlock = {
    param($sync, $installPath)

    try {
        $sync.IsRunning = $true

        $pythonDir = Join-Path $installPath "python"
        $pythonExe = Join-Path $pythonDir "python.exe"
        $pythonWExe = Join-Path $pythonDir "pythonw.exe"

        $pythonVersion = "3.11.5"
        $pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
        $getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
        $repoUrl = "https://github.com/saeedmasoudie/pywarp/archive/refs/heads/main.zip"

        # Clean previous install
        if (Test-Path $installPath) {
            Remove-Item -Path $installPath -Recurse -Force -ErrorAction SilentlyContinue
        }

        New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null

        $wc = New-Object System.Net.WebClient

        # ---------------- PYTHON ----------------
        $sync.Step = 1
        $sync.Percent = 10
        $sync.Status = "Downloading Python..."

        $pyZip = Join-Path $pythonDir "python.zip"
        $wc.DownloadFile($pythonUrl, $pyZip)

        $sync.Percent = 25
        $sync.Status = "Extracting Python..."
        [System.IO.Compression.ZipFile]::ExtractToDirectory($pyZip, $pythonDir)
        Remove-Item $pyZip

        # Enable site-packages
        $pthFile = Get-ChildItem "$pythonDir\*._pth" | Select-Object -First 1
        if ($pthFile) {
            $c = Get-Content $pthFile.FullName
            $c = $c -replace "#import site", "import site"
            $c | Set-Content $pthFile.FullName -Encoding ASCII
        }

        # ---------------- REPO ----------------
        $sync.Step = 2
        $sync.Percent = 40
        $sync.Status = "Downloading App..."

        $repoZip = Join-Path $installPath "repo.zip"
        $wc.DownloadFile($repoUrl, $repoZip)

        $sync.Percent = 50
        $sync.Status = "Extracting App..."
        [System.IO.Compression.ZipFile]::ExtractToDirectory($repoZip, $installPath)
        Remove-Item $repoZip

        $subFolder = Join-Path $installPath "pywarp-main"
        if (Test-Path $subFolder) {
            Get-ChildItem "$subFolder\*" | Move-Item -Destination $installPath -Force
            Remove-Item $subFolder -Recurse -Force
        }

        # Move resources_rc.py into python folder
        $resFile = Join-Path $installPath "resources_rc.py"
        if (Test-Path $resFile) {
            Move-Item $resFile -Destination $pythonDir -Force
        }

        # Remove unnecessary files/folders
        $itemsToRemove = @(
			".flake8",".github","CHANGELOG.md","LICENSE","README.md",
			"SECURITY.md","resources.qrc","screenshots",
			"translations", "installers","version.json"
		)

        foreach ($item in $itemsToRemove) {
            $pathToRemove = Join-Path $installPath $item
            if (Test-Path $pathToRemove) {
                Remove-Item $pathToRemove -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        # ---------------- PIP + DEPENDENCIES ----------------
        $sync.Step = 3
        $sync.Percent = 65
        $sync.Status = "Installing pip..."

        $getPip = Join-Path $pythonDir "get-pip.py"
        $wc.DownloadFile($getPipUrl, $getPip)

        Start-Process -FilePath $pythonExe -ArgumentList "`"$getPip`"" -Wait -NoNewWindow
        Remove-Item $getPip

        # Install PySide6
        $sync.Percent = 80
		$sync.Status = "Installing dependencies..."

		$reqFile = Join-Path $installPath "requirements.txt"
		if (Test-Path $reqFile) {
			Start-Process -FilePath $pythonExe `
				-ArgumentList "-m pip install -r `"$reqFile`"" `
				-Wait -NoNewWindow
		}
		Remove-Item $reqFile -Force -ErrorAction SilentlyContinue

        # ---------------- SHORTCUT ----------------
        $sync.Step = 4
        $sync.Percent = 95
        $sync.Status = "Creating Shortcut..."

        $WshShell = New-Object -comObject WScript.Shell
        $DesktopPath = $WshShell.SpecialFolders.Item("Desktop")

        $Shortcut = $WshShell.CreateShortcut("$DesktopPath\PyWarp.lnk")
        $Shortcut.TargetPath = $pythonWExe
        $Shortcut.Arguments = "`"$installPath\main.py`""
        $Shortcut.WorkingDirectory = $installPath

        $iconFile = Join-Path $installPath "assets\logo.ico"
        if (Test-Path $iconFile) {
            $Shortcut.IconLocation = $iconFile
        }

        $Shortcut.Save()

        $sync.Percent = 100
        $sync.Status = "Installation Complete!"
        $sync.IsComplete = $true
    }
    catch {
        $sync.Error = $_.Exception.Message
    }
    finally {
        $sync.IsRunning = $false
        if ($wc) { $wc.Dispose() }
    }
}

# Timer
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
    Call-JS "setProgress" @($syncHash.Percent, "$($syncHash.Status)")
    if ($syncHash.Step -gt 0) { Call-JS "setActiveStep" @($syncHash.Step) }
    if ($syncHash.IsComplete) { $timer.Stop(); Call-JS "installComplete" @() }
    if ($syncHash.Error) { $timer.Stop(); Call-JS "setProgress" @(0, "Error: " + $syncHash.Error) }
})

$bridge.OnClose = { $form.Close() }
$bridge.OnStartInstall = {
    param($installPath)
    if (-not $syncHash.IsRunning) {
        $ps = [PowerShell]::Create()
        $ps.AddScript($installScriptBlock).AddArgument($syncHash).AddArgument($installPath) | Out-Null
        $ps.BeginInvoke()
        $timer.Start()
    }
}

[System.Windows.Forms.Application]::EnableVisualStyles()
$form.ShowDialog() | Out-Null
