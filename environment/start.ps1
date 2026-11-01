# Windows entry point. PowerShell 5.1 is sufficient; Python is optional initially.
# Do not declare parameters: application options must remain ordinary arguments.
$ErrorActionPreference = 'Stop'
$WhutArguments = @($args | ForEach-Object { [string]$_ })
$WhutEnvironmentDir = $PSScriptRoot

function Write-WhutLog([string]$Message) {
    [Console]::Error.WriteLine('[LLM4Ship] ' + $Message)
}

function ConvertTo-WhutNativeArgument([string]$Value) {
    # Windows CommandLineToArgvW/CRT escaping. No command shell parses this string.
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $slashes++
        } elseif ($character -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
            [void]$builder.Append('"')
            $slashes = 0
        } else {
            if ($slashes) { [void]$builder.Append(('\' * $slashes)) }
            [void]$builder.Append($character)
            $slashes = 0
        }
    }
    if ($slashes) { [void]$builder.Append(('\' * (2 * $slashes))) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function New-WhutProcess([string]$Executable, [string[]]$Arguments) {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-WhutNativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.WorkingDirectory = (Get-Location).ProviderPath
    $start.EnvironmentVariables['PYTHONUTF8'] = '1'
    $start.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $start.EnvironmentVariables['PYTHONUNBUFFERED'] = '1'
    $start.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
    $start.EnvironmentVariables.Remove('PYTHONHOME')
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    return $process
}

function Resolve-WhutPython([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    $expanded = [Environment]::ExpandEnvironmentVariables($Value)
    if (Test-Path -LiteralPath $expanded -PathType Leaf) {
        return (Resolve-Path -LiteralPath $expanded).ProviderPath
    }
    $found = Get-Command -Name $expanded -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.Source }
    return $null
}

function Test-WhutPython([string]$Executable) {
    if (-not $Executable -or $Executable -match '\\WindowsApps\\') { return $false }
    $process = $null
    try {
        $process = New-WhutProcess $Executable @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 2)')
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        [void]$process.Start()
        if (-not $process.WaitForExit(15000)) { $process.Kill(); return $false }
        return $process.ExitCode -eq 0
    } catch { return $false }
    finally { if ($process) { $process.Dispose() } }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Automatic runtime setup requires Windows x86-64.'
    }
    $explicit = $null
    $runtimeOverride = $env:WHUTOCEANSHIP_RUNTIME_ROOT
    $isolated = $WhutArguments -contains '--isolated'
    for ($index = 0; $index -lt $WhutArguments.Count; $index++) {
        if ($WhutArguments[$index] -eq '--') { break }
        if ($WhutArguments[$index] -eq '--python') {
            if ($index + 1 -ge $WhutArguments.Count) { throw '--python requires an executable path.' }
            $explicit = $WhutArguments[$index + 1]
        } elseif ($WhutArguments[$index].StartsWith('--python=')) {
            $explicit = $WhutArguments[$index].Substring(9)
        } elseif ($WhutArguments[$index] -eq '--runtime-dir') {
            if ($index + 1 -ge $WhutArguments.Count) { throw '--runtime-dir requires a path.' }
            $runtimeOverride = $WhutArguments[$index + 1]
        } elseif ($WhutArguments[$index].StartsWith('--runtime-dir=')) {
            $runtimeOverride = $WhutArguments[$index].Substring(14)
        }
    }
    if (-not $explicit -and -not $isolated) { $explicit = $env:WHUTOCEANSHIP_PYTHON }
    $python = $null
    if ($explicit) {
        $python = Resolve-WhutPython $explicit
        if (-not (Test-WhutPython $python)) {
            throw "Requested Python is missing or cannot start Python 3.9+: $explicit. The selected environment was not changed."
        }
    }
    $cache = $env:WHUTOCEANSHIP_CACHE
    if (-not $cache) {
        $localBase = $env:LOCALAPPDATA
        if (-not $localBase) { $localBase = Join-Path $env:USERPROFILE 'AppData\Local' }
        $cache = Join-Path $localBase 'WhutOceanShip-Skills'
    }
    $miniforge = Join-Path $cache 'bootstrap\miniforge3'
    if (-not $python) {
        $candidates = @(
            'D:\anaconda3\envs\mypythorch\python.exe',
            $env:CONDA_PYTHON_EXE,
            (Join-Path $miniforge 'python.exe'),
            (Join-Path (Split-Path $WhutEnvironmentDir -Parent) 'runtime\env\python.exe'),
            'python.exe', 'python3.exe',
            'D:\anaconda3\python.exe',
            (Join-Path $env:USERPROFILE 'miniforge3\python.exe'),
            (Join-Path $env:USERPROFILE 'miniconda3\python.exe'),
            (Join-Path $env:USERPROFILE 'anaconda3\python.exe')
        )
        if ($runtimeOverride) { $candidates = @((Join-Path $runtimeOverride 'env\python.exe')) + $candidates }
        $condaCandidates = @($env:CONDA_EXE)
        foreach ($condaName in @('conda.exe', 'conda.bat')) {
            $foundConda = Get-Command -Name $condaName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($foundConda) { $condaCandidates += $foundConda.Source }
        }
        foreach ($condaPath in $condaCandidates) {
            if ($condaPath -and (Test-Path -LiteralPath $condaPath -PathType Leaf)) {
                $condaParent = Split-Path $condaPath -Parent
                $candidates += (Join-Path (Split-Path $condaParent -Parent) 'python.exe')
                $candidates += (Join-Path $condaParent 'python.exe')
            }
        }
        foreach ($candidate in $candidates) {
            $resolved = Resolve-WhutPython $candidate
            if (Test-WhutPython $resolved) { $python = $resolved; break }
        }
    }
    if (-not $python) {
        $launcher = Get-Command -Name 'py.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($launcher) {
            $probe = New-WhutProcess $launcher.Source @('-3', '-c', 'import sys; print(sys.executable) if sys.version_info >= (3,9) else sys.exit(2)')
            $probe.StartInfo.RedirectStandardOutput = $true
            $probe.StartInfo.RedirectStandardError = $true
            $probe.StartInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
            try {
                [void]$probe.Start()
                if (-not $probe.WaitForExit(15000)) { $probe.Kill() }
                elseif ($probe.ExitCode -eq 0) {
                    $resolved = $probe.StandardOutput.ReadToEnd().Trim()
                    if (Test-WhutPython $resolved) { $python = $resolved }
                }
            } finally { $probe.Dispose() }
        }
    }
    if (-not $python) {
        if ($WhutArguments -contains '--check') {
            throw 'No usable Python was found. --check never installs software. Run --setup to prepare an isolated runtime.'
        }
        Write-WhutLog 'No Python was found; preparing the official isolated Miniforge bootstrap.'
        & (Join-Path $WhutEnvironmentDir 'install-miniforge.ps1') -Prefix $miniforge
        $python = Join-Path $miniforge 'python.exe'
        if (-not (Test-WhutPython $python)) { throw "Installed bootstrap Python did not start: $python" }
    }
    $process = New-WhutProcess $python (@((Join-Path $WhutEnvironmentDir 'bootstrap.py')) + $WhutArguments)
    [void]$process.Start()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $process.Dispose()
    exit $exitCode
} catch {
    Write-WhutLog ('ERROR: ' + $_.Exception.Message)
    exit 2
}
