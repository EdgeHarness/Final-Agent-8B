<#
Build llama.cpp for Snapdragon X Elite (Windows on Arm, ARM64 native).

Run this ON the Lenovo, from an "ARM64 Native Tools Command Prompt for VS 2022"
shell (or any shell where clang for ARM64 and cmake are on PATH).

    .\build-xelite.ps1                 # CPU only  (recommended)
    .\build-xelite.ps1 -Opencl         # also build the Adreno OpenCL backend
    .\build-xelite.ps1 -Src D:\src\llama.cpp

Why these settings: see README.md. Short version — the stock
`arm64-windows-llvm` toolchain already compiles with `-march=armv8.7-a`, which
is exactly the Oryon ISA level, so the CPU baseline is correct out of the box.
The wins here are KleidiAI's i8mm/dotprod matmul microkernels, OpenMP off, and
LTO.
#>
[CmdletBinding()]
param(
    [string]$Src = "$PSScriptRoot\llama.cpp",
    [switch]$Opencl,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Need($exe, $hint) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) {
        throw "'$exe' not found on PATH. $hint"
    }
}

Need cmake  "Install CMake (winget install Kitware.CMake)."
Need ninja  "Install Ninja (winget install Ninja-build.Ninja)."
Need clang  "Install LLVM for ARM64 (winget install LLVM.LLVM), or run from an ARM64 Native Tools prompt."

if ($env:PROCESSOR_ARCHITECTURE -ne "ARM64") {
    Write-Warning "PROCESSOR_ARCHITECTURE is '$env:PROCESSOR_ARCHITECTURE', not ARM64."
    Write-Warning "You are probably in an x64-emulated shell. The build will be slow and may target the wrong arch."
}

# --- source ---------------------------------------------------------------
if (-not (Test-Path $Src)) {
    Write-Host "==> cloning llama.cpp into $Src"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp $Src
} else {
    Write-Host "==> using existing checkout $Src"
}

# The presets below inherit from llama.cpp's own arm64-windows-llvm-release,
# so CMakeUserPresets.json has to sit next to its CMakePresets.json.
Copy-Item "$PSScriptRoot\CMakeUserPresets.json" $Src -Force

$preset = if ($Opencl) { "xelite-opencl" } else { "xelite-cpu" }
$build  = "$Src\build-$preset"

if ($Clean -and (Test-Path $build)) {
    Write-Host "==> removing $build"
    Remove-Item -Recurse -Force $build
}

if ($Opencl) {
    if (-not $env:OPENCL_SDK_ROOT) {
        Write-Warning "OPENCL_SDK_ROOT is not set. The Adreno OpenCL backend needs the"
        Write-Warning "Qualcomm OpenCL SDK; configure will likely fail to find CL headers."
    }
}

Push-Location $Src
try {
    Write-Host "==> configure  ($preset)"
    cmake --preset $preset -B $build
    if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }

    Write-Host "==> build  (12 Oryon cores)"
    cmake --build $build --config Release -j 12
    if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }
} finally {
    Pop-Location
}

$bin = Join-Path $build "bin\Release"
if (-not (Test-Path $bin)) { $bin = Join-Path $build "bin" }

Write-Host ""
Write-Host "==> binaries in $bin"
Get-ChildItem $bin -Filter "llama-*.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 12 | ForEach-Object { Write-Host "      $($_.Name)" }

Write-Host ""
Write-Host "Confirm the CPU features the build actually detected:"
Write-Host "    & '$bin\llama-cli.exe' --version"
Write-Host "Expect NEON = 1, DOTPROD = 1, MATMUL_INT8 = 1, SVE = 0, SME = 0."
Write-Host ""
Write-Host "Next:  .\bench-xelite.ps1 -Bin '$bin' -Model <path-to.gguf>"
