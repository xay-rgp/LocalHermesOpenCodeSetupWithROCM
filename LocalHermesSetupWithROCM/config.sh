# Edit this file, then run: bash setup.sh
# Bash syntax: one quoted Ollama model name per line. These names are also
# used in the Ollama launcher. Old model downloads are NOT deleted.
MODELS=(
  "qwen3-coder:30b"
  "huihui_ai/Qwen3.8-abliterated:27b"
  "prutser/gemma-4-26B-A4B-it-ara-abliterated:Q4_K_S"
)
DEFAULT_MODEL="prutser/gemma-4-26B-A4B-it-ara-abliterated:Q4_K_S"

# Tuned Ollama alias built locally from DEFAULT_MODEL (zero extra disk space).
# Forces 100% GPU offload (num_gpu 999) and optimal prefill batch (num_batch 512)
# so Ollama's default VRAM margin does not spill MoE experts to CPU RAM.
# Set TUNED_MODEL_NAME="" to disable creating an alias and use DEFAULT_MODEL directly.
TUNED_MODEL_NAME="gemma-4-26b-fast:Q4_K_S"
TUNED_MODEL_NUM_GPU=999
TUNED_MODEL_NUM_BATCH=512

# Shared Ollama service allocation and Hermes model.context_length.
# Keep these equal so Hermes compacts before Ollama truncates user messages.
# 32K context with q4_0 KV cache keeps 15 GB Q4_K_S models 100% in 16 GB VRAM.
CONTEXT_LENGTH=32768
# Only expose this RX 9060 XT to Ollama. On another machine, replace the UUID
# with its GPU's Uuid from: sudo -u ollama /opt/rocm/bin/rocminfo
ROCM_GPU_UUID="GPU-4f3288ca66e47853"
KEEP_ALIVE="30m" # Avoid model reloads between nearby conversations.
FLASH_ATTENTION=1
KV_CACHE_TYPE="q4_0"  # ~1/4 of f16 KV memory; use q8_0 or f16 if quality regresses
# AMD discrete GPU power profile via sysfs (5 = COMPUTE removes clock ramp-up lag; empty to skip).
GPU_POWER_PROFILE=5

# Opt in with: PERFORMANCE_PROFILE=speed bash setup.sh --tune-only
# A smaller context leaves more VRAM for model layers, reducing CPU offload.
PERFORMANCE_PROFILE="${PERFORMANCE_PROFILE:-custom}"
case "$PERFORMANCE_PROFILE" in
  custom) ;;
  speed)
    CONTEXT_LENGTH=32768
    FLASH_ATTENTION=1
    KV_CACHE_TYPE="q4_0"
    KEEP_ALIVE="30m"
    ;;
  *) echo 'PERFORMANCE_PROFILE must be custom or speed.' >&2; return 1 ;;
esac

# Hermes release channel: stable releases or the development main branch.
HERMES_CHANNEL="stable"
