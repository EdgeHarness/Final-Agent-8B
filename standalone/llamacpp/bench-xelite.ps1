<#
Find the fastest runtime settings for THIS machine. Do not trust the defaults
in serve-xelite.ps1 blindly — measure, then edit them.

    .\bench-xelite.ps1 -Bin ..\llama.cpp\build-xelite-cpu\bin\Release `
                       -Model C:\models\Meta-Llama-3.1-8B-Instruct-Q4_0.gguf

What it measures, and why each one matters on Oryon:

  1. Thread sweep. The X Elite has 12 identical Oryon cores in 3 clusters of 4
     — there are no efficiency cores, so there is no "use only the P-cores"
     answer. Prefill is compute-bound and usually wants all 12. Decode is
     memory-bound at 135 GB/s and often peaks BELOW 12, because extra threads
     add contention without adding bandwidth. That is why serve-xelite.ps1
     splits -t (decode) from -tb (prefill).

  2. KV cache quantization. q8_0 halves KV traffic. On a bandwidth-bound
     decode that can be a real gain, and 8-bit KV is close to lossless.

  3. mmap off. Q4_0 is repacked into i8mm-interleaved layout at load time;
     with mmap on you can end up paying for both copies.

IMPORTANT: plug the laptop in and set Windows to "Best Performance" first.
Oryon clocks drop hard on battery and every number below will be wrong.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Bin,
    [Parameter(Mandatory)][string]$Model,
    [string]$Threads = "6,8,10,12",
    [int]$Prompt = 512,
    [int]$Gen = 128,
    [string]$Out = "$PSScriptRoot\bench-results.md"
)

$ErrorActionPreference = "Stop"
$bench = Join-Path $Bin "llama-bench.exe"
if (-not (Test-Path $bench)) { throw "llama-bench.exe not found in $Bin" }
if (-not (Test-Path $Model)) { throw "model not found: $Model" }

$onBattery = (Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue).BatteryStatus -eq 1
if ($onBattery) { Write-Warning "Running on battery — results will understate the chip. Plug in." }

"# llama.cpp on Snapdragon X Elite — $(Get-Date -Format s)" | Set-Content $Out
"", "Model: ``$(Split-Path $Model -Leaf)``", "" | Add-Content $Out

function Run($label, $bargs) {
    Write-Host ""
    Write-Host "==> $label" -ForegroundColor Cyan
    Write-Host "    llama-bench $($bargs -join ' ')"
    "## $label", "", '```' | Add-Content $Out
    & $bench @bargs 2>&1 | Tee-Object -Variable out | Write-Host
    $out | Add-Content $Out
    '```', "" | Add-Content $Out
}

# 1. thread sweep, mmap off, flash attention on
Run "Thread sweep (-t $Threads)" @(
    "-m", $Model, "-t", $Threads, "-p", $Prompt, "-n", $Gen, "-fa", "1", "-mmp", "0"
)

# 2. KV cache f16 vs q8_0 at 12 threads
Run "KV cache f16 vs q8_0" @(
    "-m", $Model, "-t", "12", "-p", $Prompt, "-n", $Gen, "-fa", "1", "-mmp", "0",
    "-ctk", "f16,q8_0", "-ctv", "f16,q8_0"
)

# 3. does mmap cost anything here
Run "mmap on vs off" @(
    "-m", $Model, "-t", "12", "-p", $Prompt, "-n", $Gen, "-fa", "1", "-mmp", "0,1"
)

Write-Host ""
Write-Host "Wrote $Out" -ForegroundColor Green
Write-Host ""
Write-Host "Read it like this:"
Write-Host "  pp$Prompt = prefill (prompt processing), tok/s   -> pick the best -tb"
Write-Host "  tg$Gen  = decode (token generation), tok/s      -> pick the best -t"
Write-Host ""
Write-Host "Sanity check against the roofline: decode cannot exceed"
Write-Host "  135 GB/s / (model file size in GB) tok/s."
Write-Host "For an 8B Q4_0 (~4.7 GB) that ceiling is ~29 tok/s; ~20 tok/s is a good real result."
