<#
Start llama-server tuned for Snapdragon X Elite + 32 GB.

    .\serve-xelite.ps1 -Bin ..\llama.cpp\build-xelite-cpu\bin\Release `
                       -Model C:\models\Meta-Llama-3.1-8B-Instruct-Q4_0.gguf

Defaults are the reasoned starting point, NOT measured truth for your unit.
Run bench-xelite.ps1 first and adjust -Threads / -ThreadsBatch to match.

Flag-by-flag rationale is in README.md §4.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Bin,
    [Parameter(Mandatory)][string]$Model,
    [int]$Ctx = 8192,          # matches the 8B agent profile's num_ctx
    [int]$Threads = 8,         # decode: memory-bound, often peaks below 12
    [int]$ThreadsBatch = 12,   # prefill: compute-bound, wants all 12 Oryon cores
    [int]$Batch = 2048,
    [int]$UBatch = 512,
    [string]$KvType = "q8_0",  # f16 to disable KV quantization
    [int]$Port = 8080,
    [switch]$NoMlock
)

$ErrorActionPreference = "Stop"
$server = Join-Path $Bin "llama-server.exe"
if (-not (Test-Path $server)) { throw "llama-server.exe not found in $Bin" }
if (-not (Test-Path $Model)) { throw "model not found: $Model" }

$sizeGB = [math]::Round((Get-Item $Model).Length / 1GB, 2)
$roofline = [math]::Round(135 / $sizeGB, 1)

$powerScheme = (powercfg /getactivescheme) -join ""
if ($powerScheme -notmatch "Best performance|High performance") {
    Write-Warning "Windows power scheme is not 'Best performance'. Oryon will clock down."
    Write-Warning "  Settings > System > Power & battery > Power mode > Best Performance"
}

$serverArgs = @(
    "-m", $Model
    "-c", $Ctx
    "-t", $Threads          # decode threads
    "-tb", $ThreadsBatch    # prefill/batch threads
    "-b", $Batch
    "-ub", $UBatch
    "-fa", "on"             # flash attention; also required for quantized V cache
    "-ctk", $KvType
    "-ctv", $KvType
    "--no-mmap"             # Q4_0 is repacked on load; skip the double copy
    "--host", "127.0.0.1"
    "--port", $Port
    "--jinja"               # use the GGUF's own chat template
    "-np", "1"              # one slot: the agent is strictly sequential
)
if (-not $NoMlock) { $serverArgs += "--mlock" }   # 32 GB — pin weights, never page

Write-Host ""
Write-Host "  model      $(Split-Path $Model -Leaf)  ($sizeGB GB)" -ForegroundColor Cyan
Write-Host "  decode ceiling ~$roofline tok/s  (135 GB/s LPDDR5x / $sizeGB GB)"
Write-Host "  threads    $Threads decode / $ThreadsBatch prefill"
Write-Host "  ctx        $Ctx   kv $KvType   batch $Batch/$UBatch"
Write-Host "  endpoint   http://127.0.0.1:$Port/v1/chat/completions"
Write-Host ""
Write-Host "  llama-server $($serverArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""

& $server @serverArgs
