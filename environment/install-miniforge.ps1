param([Parameter(Mandatory = $true)][string]$Prefix)

# Install only to a new private prefix. No activation, registry registration,
# system PATH edit, ExecutionPolicy change, or NVIDIA driver action is performed.
$ErrorActionPreference = 'Stop'
$Prefix = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Prefix))
$conda = Join-Path $Prefix 'Scripts\conda.exe'
if (Test-Path -LiteralPath $conda -PathType Leaf) { return }
if (Test-Path -LiteralPath $Prefix) { throw "Refusing to overwrite an existing incomplete Miniforge prefix: $Prefix" }
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'The automatic installer supports Windows x86-64 only.'
}
$release = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'miniforge-release.txt') -Raw).Trim()
if ($release -notmatch '^\d+\.\d+\.\d+-\d+$') { throw 'Invalid pinned Miniforge release.' }
$asset = "Miniforge3-$release-Windows-x86_64.exe"
$url = "https://github.com/conda-forge/miniforge/releases/download/$release/$asset"
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('WhutOceanShip-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temporary)
try {
    # TLS configuration is process-local and does not alter the operating system.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $installer = Join-Path $temporary $asset
    $checksum = Join-Path $temporary ($asset + '.sha256')
    [Console]::Error.WriteLine('[LLM4Ship] Downloading official Miniforge: ' + $url)
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer
    Invoke-WebRequest -UseBasicParsing -Uri ($url + '.sha256') -OutFile $checksum
    $match = [regex]::Match((Get-Content -LiteralPath $checksum -Raw), '\b[0-9a-fA-F]{64}\b')
    if (-not $match.Success) { throw 'The official checksum file contains no SHA-256 digest.' }
    $actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
    if ($actual -ne $match.Value) { throw 'Miniforge SHA-256 verification failed. The installer was not executed.' }
    [void][IO.Directory]::CreateDirectory((Split-Path $Prefix -Parent))
    [Console]::Error.WriteLine('[LLM4Ship] Verified installer; installing private Miniforge: ' + $Prefix)
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $installer
    $start.UseShellExecute = $false
    # NSIS requires /D to be last and the directory remainder to be unquoted.
    # FileName is separate, and no command shell evaluates the directory text.
    $start.Arguments = '/InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=' + $Prefix
    $process = [Diagnostics.Process]::Start($start)
    while (-not $process.WaitForExit(15000)) {
        [Console]::Error.WriteLine('[LLM4Ship] Miniforge installation is still running...')
    }
    $exitCode = $process.ExitCode
    $process.Dispose()
    if ($exitCode -ne 0) { throw "Miniforge installer exited with code $exitCode." }
    if (-not (Test-Path -LiteralPath $conda -PathType Leaf)) { throw "Installer did not create conda: $conda" }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
