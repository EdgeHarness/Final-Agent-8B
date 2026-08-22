# Agent 8B — task runner
#
# Wraps the agent, the Agent Lab UI and the MCP safety self-test so the long
# PowerShell invocations become one word.  Run `make` for the target list.
#
# WINDOWS ONLY, on purpose.  SHELL is powershell.exe and `doctor` reads the
# Snapdragon X Elite's cores, RAM and power plan through CIM - the box this
# agent is built to run on.  On macOS or Linux skip make and call the modules
# directly, which is all these targets do:
#
#     python -m webui.server        # = make web
#     python -m mcp.test_bridge     # = make mcp-test
#     python -m tests.test_harness  # the suite
#
# make is NOT installed by default on the lab machine:
#     winget install --id ezwinports.make
#
# Every path below is overridable on the command line:
#     make run TASK="Summarise my inbox"
#     make model MODEL=qwen2.5:14b
#
# Two backends, and they both own :11434 — never run both.
#
#   Ollama/CPU   make ollama-up | make run
#   GenieX/NPU   make npu-up | make shim | make run
#
# The NPU path serves the model on the Hexagon through GenieX (:18181, OpenAI
# API) and puts npu/ollama_shim.py in front of it on :11434, so the agent cannot
# tell which backend it is talking to. See notes/NPU Serving.md.

SHELL         := powershell.exe
.SHELLFLAGS   := -NoProfile -ExecutionPolicy Bypass -Command
.DEFAULT_GOAL := help

# ---------------------------------------------------------------- knobs ----
PY            ?= C:/Users/Lab User/SAIL/python/python.exe
MODEL         ?= llama3.1:8b
PORT          ?= 8765
TASK          ?= Find a free hour on Thursday and book it as Deep work

# NPU backend. COMPUTE is npu (pinned to one HTP session) or hybrid (per-tensor
# HTP+CPU scheduler) — Phase 2 measures both. NCTX must match the harness
# profile's num_ctx; GenieX defaults to 4096, which every profile exceeds.
NPU_MODEL     ?= ai-hub-models/Llama-v3.1-8B-Instruct
COMPUTE       ?= npu
NCTX          ?= 8192

# --------------------------------------------------------------- targets ----

help: ## Show this help
	@Write-Host ""
	@Write-Host "  Agent 8B - local agent lab" -ForegroundColor Cyan
	@Write-Host ""
	@Select-String -Path Makefile -Pattern '^([a-zA-Z0-9_.-]+):.*?## (.*)$$' | ForEach-Object { $$g = $$_.Matches[0].Groups; Write-Host ("  " + $$g[1].Value.PadRight(14) + " " + $$g[2].Value) }
	@Write-Host ""
	@Write-Host "  CPU path:    make ollama-up | make lab" -ForegroundColor DarkGray
	@Write-Host "  NPU path:    make npu-up | make shim | make lab   (stop Ollama first)" -ForegroundColor DarkGray
	@Write-Host "  Headless:    make run TASK=`"...`"" -ForegroundColor DarkGray
	@Write-Host ""

doctor: ## Check toolchain, hardware and what is running
	@Write-Host ""
	@Write-Host "  toolchain" -ForegroundColor Cyan
	@$$t = [ordered]@{ git='Git.Git'; make='ezwinports.make'; ollama='Ollama.Ollama' }; foreach ($$k in $$t.Keys) { $$c = Get-Command $$k -ErrorAction SilentlyContinue; if ($$c) { Write-Host ("    ok       " + $$k) -ForegroundColor Green } else { Write-Host ("    missing  " + $$k.PadRight(6) + " winget install --id " + $$t[$$k]) -ForegroundColor Yellow } }
	@if (Test-Path "$(PY)") { Write-Host "    ok       python" -ForegroundColor Green } else { Write-Host "    missing  python  set PY=path/to/python.exe" -ForegroundColor Yellow }
	@Write-Host ""
	@Write-Host "  python packages" -ForegroundColor Cyan
	@foreach ($$m in @('requests','pptx','openpyxl','webview')) { & "$(PY)" -c "import $$m" 2>$$null; if ($$?) { Write-Host ("    ok       " + $$m) -ForegroundColor Green } else { Write-Host ("    missing  " + $$m.PadRight(9) + "-> make pydeps") -ForegroundColor Yellow } }
	@Write-Host ""
	@Write-Host "  hardware" -ForegroundColor Cyan
	@Write-Host ("    arch     " + $$env:PROCESSOR_ARCHITECTURE)
	@Get-CimInstance Win32_Processor | ForEach-Object { Write-Host ("    cpu      " + $$_.Name.Trim() + "  (" + $$_.NumberOfCores + " cores)") }
	@Get-CimInstance Win32_ComputerSystem | ForEach-Object { Write-Host ("    ram      " + [math]::Round($$_.TotalPhysicalMemory/1GB,1) + " GB") }
	@$$p = (powercfg /getactivescheme) -join ''; if ($$p -match 'Best performance|High performance') { Write-Host "    power    Best performance" -ForegroundColor Green } else { Write-Host "    power    NOT Best performance - Oryon will clock down" -ForegroundColor Yellow }
	@Write-Host ""
	@Write-Host "  services" -ForegroundColor Cyan
	@try { $$r = Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 2; Write-Host ("    up       :11434 ollama, " + $$r.models.Count + " model(s)") -ForegroundColor Green; if ($$r.models.name -contains "$(MODEL)") { Write-Host "    ok       $(MODEL) pulled" -ForegroundColor Green } else { Write-Host "    missing  $(MODEL)  -> make model" -ForegroundColor Yellow } } catch { Write-Host "    down     :11434 ollama - the agent talks to this port  -> make ollama-up" -ForegroundColor Yellow }
	@try { $$r = Invoke-RestMethod http://127.0.0.1:18181/v1/models -TimeoutSec 2; Write-Host ("    up       :18181 geniex, " + $$r.data.Count + " model(s) - NPU backend") -ForegroundColor Green } catch { Write-Host "    down     :18181 geniex  -> make npu-up  (only if serving on the NPU)" -ForegroundColor DarkGray }
	@try { $$null = Invoke-WebRequest http://127.0.0.1:$(PORT)/api/status -TimeoutSec 2 -UseBasicParsing; Write-Host "    up       :$(PORT) agent lab" -ForegroundColor Green } catch { Write-Host "    down     :$(PORT) agent lab  -> make lab" -ForegroundColor DarkGray }
	@Write-Host ""

pydeps: ## Install the agent's Python packages
	@& "$(PY)" -m pip install --upgrade requests python-pptx openpyxl pywebview

model: ## Pull the agent's model into Ollama (override MODEL=tag)
	@ollama pull $(MODEL)

ollama-up: ## Start Ollama (CPU backend, owns :11434)
	@try { $$null = Invoke-WebRequest http://127.0.0.1:11434/api/version -TimeoutSec 2 -UseBasicParsing; Write-Host "ollama already up on :11434" } catch { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden; Write-Host "ollama serve started on :11434" }

npu-pull: ## Fetch the NPU model bundle (override NPU_MODEL=...)
	@geniex pull "$(NPU_MODEL)"

npu-up: ## Serve the model on the Hexagon NPU via GenieX (:18181)
	@try { $$null = Invoke-WebRequest http://127.0.0.1:18181/v1/models -TimeoutSec 2 -UseBasicParsing; Write-Host "geniex already up on :18181" } catch { Start-Process geniex -ArgumentList 'serve','--compute','$(COMPUTE)','--nctx','$(NCTX)' -WindowStyle Hidden; Write-Host "geniex serve started on :18181 (--compute $(COMPUTE) --nctx $(NCTX))" }

shim: ## Ollama-API shim in front of GenieX (:11434) - stop Ollama first
	@& "$(PY)" -m npu.ollama_shim

lab: ## Agent Lab in a desktop window (falls back to the browser)
	@& "$(PY)" -m webui.app

web: ## Agent Lab in a browser tab instead of a window
	@& "$(PY)" -m webui.server

run: ## Run the agent headless. Override with TASK="..."
	@& "./agents/8b/run.ps1" "$(TASK)"

mcp-test: ## Assert the MCP safety guarantees (no credentials needed)
	@& "$(PY)" -m mcp.test_bridge

.PHONY: help doctor pydeps model ollama-up npu-pull npu-up shim lab web run mcp-test
