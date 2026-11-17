# Edit this file, then run: bash setup.sh
# Bash syntax: one quoted Ollama model name per line. These names are also
# used in the Ollama launcher. Old model downloads are NOT deleted.
MODELS=(
  "qwen3-coder:30b"
  "huihui_ai/Qwen3.8-abliterated:27b"
)
DEFAULT_MODEL="${MODELS[0]}"

# Shared Ollama service allocation and Hermes model.context_length.
# Keep these equal so Hermes compacts before Ollama truncates user messages.
# 128K requested context (doubled from 64K).
# Larger values increase cache memory and CPU offload.
CONTEXT_LENGTH=131072
# Only expose this RX 9060 XT to Ollama. On another machine, replace the UUID
# with its GPU's Uuid from: sudo -u ollama /opt/rocm/bin/rocminfo
ROCM_GPU_UUID="GPU-4f3288ca66e47853"
KEEP_ALIVE="30m" # Avoid model reloads between nearby conversations; not a decode-speed gain.
FLASH_ATTENTION=1
KV_CACHE_TYPE="q8_0"  # roughly half the f16 KV memory; use f16 if quality regresses

# Opt in with: PERFORMANCE_PROFILE=speed bash setup.sh --tune-only
# A smaller context leaves more VRAM for model layers, reducing CPU offload.
# Keep custom as the default to preserve the requested 128K context.
PERFORMANCE_PROFILE="${PERFORMANCE_PROFILE:-custom}"
case "$PERFORMANCE_PROFILE" in
  custom) ;;
  speed)
    CONTEXT_LENGTH=32768
    FLASH_ATTENTION=1
    KV_CACHE_TYPE="q8_0"
    KEEP_ALIVE="30m"
    ;;
  *) echo 'PERFORMANCE_PROFILE must be custom or speed.' >&2; return 1 ;;
esac

# Hermes release channel: stable releases or the development main branch.
HERMES_CHANNEL="stable"
