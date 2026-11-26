# Local model setup: Arch Linux + AMD ROCm

Installs Ollama with ROCm, your configured local models, Hermes Agent, and OpenCode. Written for your Arch Linux x86_64 / RX 9060 XT setup.
It can also run on another Arch x86_64 machine with a supported AMD GPU;
it is not an Ubuntu, NVIDIA, macOS, or Windows installer.

## Run from Bash or Fish

```sh
bash /home/xay/LocalHermesSetupWithROCM/setup.sh --dry-run
bash /home/xay/LocalHermesSetupWithROCM/setup.sh
```

Run as your regular user, **not** `sudo bash`. The script requests sudo for
system packages, the service configuration, and reading GPU verification logs.
It performs `pacman -Syu --needed ...` (a full Arch upgrade) with pacman's usual
confirmation, then enables/restarts Ollama. Finish active generations first.
Downloads include the three model files plus ROCm and agent packages;
existing Ollama blobs are reused. Internet access is required.

Open a fresh terminal afterward. Hermes uses local Ollama at `127.0.0.1:11434`;
no paid API key is needed for local inference. Agent behavior depends on model
tool support.

Start Hermes in your project directory with `hermes`. The installer selects
local Ollama, `DEFAULT_MODEL`, and the bundled white theme (including the ASCII
logo and Hermes-Agent banner). Use `/model MODEL` inside Hermes to select
another downloaded model, or `hermes config` to inspect settings. See the
[official local Ollama guide](https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup).

## Change models or settings

Edit **config.sh**, the only file needed for ordinary changes:

```bash
MODELS=(
  "qwen3-coder:30b"
  "huihui_ai/Qwen3.8-abliterated:27b"
  "prutser/gemma-4-26B-A4B-it-ara-abliterated:Q4_K_S"
)
DEFAULT_MODEL="${MODELS[0]}"
CONTEXT_LENGTH=131072
```

Add/remove model lines, change the default, and rerun `bash setup.sh`. It pulls
the selected models and sets Hermes’s default model. It **never deletes old
model downloads**; remove unwanted ones yourself with `ollama rm NAME`.
Use local models with tool support and a context window at least as large as
`CONTEXT_LENGTH`.

The current configuration requests a 131,072-token context. Larger contexts
increase cache memory and may increase CPU offloading on this 16 GB GPU. It configures Ollama's `OLLAMA_CONTEXT_LENGTH` and Hermes' `model.context_length`.
Hermes manages its own context compaction; this script does not set Hermes output
limits or compaction thresholds.
An overstated Hermes limit (for example, 262,144 when Ollama runs at 65,536)
can delay compaction until Ollama truncates the user message and returns
`HTTP 500: no user query found in messages`. Configuration replaces stale
Hermes context limits with `CONTEXT_LENGTH` while preserving compression settings.
Automatic compression must remain enabled in Hermes for this to prevent growing
conversations from exhausting the window; existing disabled compression is not overridden.

Ollama uses Flash Attention and a `q8_0` KV cache by default, with one parallel
request and one loaded model. Q8 uses roughly half the KV-cache memory of f16,
with a small precision tradeoff. This frees memory for model layers, but does
not guarantee that a 27B/30B model fits entirely on the GPU or a particular
speed. Set `KV_CACHE_TYPE="f16"` if quality regresses; quantized cache requires
`FLASH_ATTENTION=1`. See the [Ollama FAQ](https://docs.ollama.com/faq).
`KEEP_ALIVE` must be a positive duration such as `10m`; immediate unloading
would prevent the post-generation GPU/context check.

Apply tuning to an existing installation without upgrades, model downloads,
or agent reinstalls:

```sh
bash /home/xay/LocalHermesSetupWithROCM/setup.sh --tune-only
```

Finish active work first: this restarts Ollama, verifies default-model inference
and context, then updates Hermes settings with backups. Restart Hermes after
it finishes. Prefer a new session for completed work. If an old conversation
exceeds the new context, compact it **before** reducing the server limit; a
summary request for an oversized transcript may itself exceed that limit.
Compaction summarizes history; it does not delete project files.

`bash setup.sh --configure-only` updates Hermes settings and Bash/Fish PATH
files without downloading, installing packages, or restarting Ollama. Use this
only if the models are already installed and the service already has the
desired context length. Use `--tune-only` when changing server memory settings.

`HERMES_CHANNEL="stable"` installs the stable Hermes release channel; use
`"main"` for the development branch. The official installer manages Hermes'
Python environment and runtime dependencies. It runs without the interactive
setup wizard because this script configures the local provider afterward.
`--configure-only` and `--tune-only` require Python with PyYAML already installed
(`python-yaml` on Arch); normal installation installs this dependency.

## What changes

- System packages: Ollama, its ROCm backend, OpenCode (`opencode`), Git, curl, tar, Python, PyYAML.
- `/etc/systemd/system/ollama.service.d/zz-local-model-setup.conf`: disables
  Vulkan to choose ROCm, sets loopback binding, context, one parallel request,
  one loaded model, Flash Attention, Q8 KV cache, and keep-alive. It leaves the existing model-store path
  alone. Its name sorts after the existing `context.conf` and the older
  `90-local-model-setup.conf`, which are preserved. Later overrides can still
  affect the service; verification checks systemd Environment values for context,
  host, backend selection, concurrency, Flash Attention, and KV cache. Loaded
  context and GPU allocation are also checked through the API.
- Hermes Agent: the official installer publishes `hermes` in `~/.local/bin`
  and manages its own runtime dependencies.
- `~/.hermes/config.yaml`: custom local Ollama endpoint, placeholder API key,
  default model, chat-completions API mode, and context length. `HERMES_HOME` overrides the configuration
  directory for both installation and configuration.
- `~/.config/opencode/`: deploys bundled `opencode.json` (model, compaction, and
  local Ollama provider models synced with `CONTEXT_LENGTH`), `cli.json`
  (`mercury` theme and `@rashidrazak/opencode-status-line` plugin), and all
  bundled `skills/` files. Existing unrelated keys and extra plugins are
  preserved; `service.json`, `AGENTS.md`, and `memories/` are never overwritten.
- `~/.ollama/config.json`: Hermes launch selections.
- Bash startup files plus `~/.config/fish/conf.d/local-model-setup.fish`:
  make the installed Hermes command available in new terminals.

Changed existing configuration files receive timestamped `.backup-*` siblings.
Unrelated YAML/JSON settings, permissions, other providers, and existing plugin
entries are preserved. YAML comments and formatting are normalized when saved;
the original file is kept in its backup. Tool approval settings are unchanged.
Configuration is validated before service changes (after package installation
in a full install). Malformed settings and unsupported output symlinks fail
before configuration writes. Network readiness checks have per-request timeouts.
Repeated configuration runs make no writes when nothing changes. A failed
installation stops with an error; completed packages/downloads remain and
the script can be rerun. There is no automatic transaction rollback.

To undo the service configuration, remove only the drop-in named above and
run `sudo systemctl daemon-reload` and `sudo systemctl restart ollama`.
Older drop-ins (including `context.conf`) then take effect again.
Restore individual YAML, JSON, or shell files from their backups as needed.
Cline, Pi, and Ponytail are no longer installed or configured. Their existing
packages, settings, sessions, and Ollama launcher entries are left untouched;
this script does not uninstall previous agents.

## Verification and tests

Before applying agent settings in installation and tuning modes, verify.py checks default-model tool support and
requires a completed, nonempty generation,
checks `/api/ps` GPU allocation and loaded context against `CONTEXT_LENGTH`,
and checks ROCm detection in the current
systemd invocation's logs. The inference probe uses Ollama's native `/api/generate`
endpoint; it does not exercise Hermes's `/v1/chat/completions` requests, streaming,
or multi-step tool calls. Those still need an end-to-end Hermes session.
Other models are downloaded and listed but are not loaded for inference tests.

Offline configuration tests, Bash/Python syntax checks, and dry-run are available
below. Live ROCm performance must be checked on the host after applying tuning;
the shell installer is exercised with simulated system commands, not real package
installation or GPU execution.

Offline development checks (no system changes):

```sh
cd /home/xay/LocalHermesSetupWithROCM
bash -n setup.sh config.sh
python -B -m unittest -v
bash setup.sh --dry-run
```

Files: config.sh contains preferences; setup.sh orchestrates installation;
configure.py handles backed-up YAML/JSON/shell edits; verify.py checks GPU inference;
test_configure.py tests configuration preservation, repeat runs and model changes;
test_verify.py tests service conflicts, model capability/context overrides, and GPU checks;
test_setup.py exercises install/tune/configure modes and failure paths with
simulated external commands and isolated home directories.

## Official references

- [Arch Ollama ROCm package](https://archlinux.org/packages/extra/x86_64/ollama-rocm/)
- [Hermes installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
- [Hermes local Ollama setup](https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup)

## Audit limits

The offline suite verifies configuration, shell orchestration, failure handling,
backups, permissions, and repeat runs. The installed Hermes runtime resolver was
also checked with an isolated generated configuration. Full installation and
live GPU inference still require a host with working downloads, systemd access,
and a reachable Ollama service. `hermes --version` and GPU verification run at
the end of installation; failures stop the script rather than reporting success.
Existing Hermes environment overrides (such as `CUSTOM_BASE_URL`), custom
profiles, and auxiliary-provider settings can change runtime routing; this setup
preserves those unrelated settings. The generated default model configuration
targets local Ollama. Optional external tools may require their own services.

## OpenCode

`setup.sh` installs the `opencode` package from Arch's `extra` repository and
`configure.py` deploys the bundled configuration in `opencode/` into
`~/.config/opencode/`:

- `opencode.json`: sets default/small models, compaction settings, and registers
  all configured/discovered local Ollama models with `CONTEXT_LENGTH` context
  limits while preserving unrelated settings.
- `cli.json`: sets the `mercury` theme and ensures `@rashidrazak/opencode-status-line`
  is enabled while preserving any additional user plugins.
- `skills/`: deploys all bundled OpenCode skills atomically with backups on change.

`service.json` (local service password) and personal `AGENTS.md` / `memories/`
files are not bundled and are left untouched if already present. Run
`bash setup.sh --configure-only` to redeploy OpenCode and Hermes configs without
reinstalling packages or restarting Ollama.

## White theme

All setup modes that configure Hermes install `skins/white.yaml` into
`$HERMES_HOME/skins` (default: `~/.hermes/skins`) and set `display.skin: white`.
Existing changed files are backed up; other display settings are preserved.
Restart Hermes to apply the theme.

Installed Ollama models are discovered automatically when configuring Hermes and added
to the **Local Ollama** model picker catalog alongside the models in `config.sh`.
Discovery uses the local API, with an on-disk fallback for Arch installations.
The white skin is installed and selected by default, including white logo, banner,
text and borders. Apply these settings without reinstalling or restarting Ollama:

```bash
bash setup.sh --configure-only
```

Verification reads current-invocation logs directly, then tries `sudo -n`.
If journal access is unavailable, it exits with a recovery message instead of a
Python traceback; run `sudo -v` before rerunning verification or setup.

## Select the RX 9060 XT

`config.sh` sets `ROCM_GPU_UUID="GPU-4f3288ca66e47853"` for this machine's
RX 9060 XT. Install and `--tune-only` modes write it as
`ROCR_VISIBLE_DEVICES` in the managed Ollama systemd drop-in, so Ollama's ROCm
runtime sees only that GPU. CPU offloading can still occur when VRAM is full.
On another machine, replace this UUID with the desired GPU's `Uuid` from
`sudo -u ollama /opt/rocm/bin/rocminfo` before running setup.

From the repository root, apply without reinstalling or downloading models:

```sh
bash LocalHermesSetupWithROCM/setup.sh --tune-only
```

This restarts Ollama and verifies the effective GPU selection, GPU allocation,
and configured context before updating Hermes. `--configure-only` does not
apply GPU selection. Existing later overrides (including a manually created
`zz-rx9060xt.conf`) are preserved; verification rejects a conflicting UUID.
Update such an override as well if you change the selected GPU.

UUID selection does not guarantee that live GPU detachment for VM passthrough
will leave ROCm healthy. If `rocminfo` fails after passthrough and kernel logs
show GPU reset failures, save work and reboot before retesting with the VM off.
The successful 4K-context smoke test does not establish performance at the
configured 128K context; setup verifies inference at the configured context.

## Conversation memory

Setup enables Hermes' built-in memory and user profile, adds conversation recall
instructions to `SOUL.md`, and initializes missing `memories/MEMORY.md` and
`memories/USER.md` files under `$HERMES_HOME` (default: `~/.hermes`). Existing
notes, personality text, memory limits, approval settings, and `state.db`
conversation history are preserved. Changed files are backed up; repeat runs
do not duplicate the instructions. If an existing memory limit is too small for
an initial note, setup creates an empty store and keeps recall instructions in
`SOUL.md`.

Apply this to an existing installation with `bash setup.sh --configure-only`
from the script directory, then start a fresh Hermes session or use `/new`.
This mode also applies the model, context, theme, and shell settings described
above. Saved notes load at session start; `session_search` can retrieve older
conversations already in this Hermes home's database. Setup does not summarize
all previous chats or import history from other profiles. Saving and recalling
facts still depends on the model using Hermes' memory tools. If you explicitly
disabled the `memory` or `session_search` toolsets, enable them in `hermes tools`.

## Performance tuning and measurement

`PERFORMANCE_PROFILE=speed` selects a 32,768-token context, Flash Attention,
Q8 KV cache, and a 30-minute keep-alive. Reducing context can leave more VRAM
for model layers and reduce CPU offloading. It also makes Hermes compact long
conversations sooner. It does not change the model or its weight quantization.
The default `custom` profile retains the requested 131,072-token context.
Keep-alive is now 30 minutes for both profiles; this reduces reload delays,
not steady-state decoding time, and holds GPU memory longer.

From the script directory, apply the speed preset to an existing install:

```sh
PERFORMANCE_PROFILE=speed bash setup.sh --tune-only
```

Use the same profile on subsequent setup runs, or change its default in
`config.sh` to `speed`. Tuning restarts Ollama. Start a fresh Hermes session
afterward; compact an oversized existing session before reducing context.
`--configure-only` does not apply the corresponding Ollama service settings.

Measure before and after using the same model and otherwise idle machine:

```sh
python benchmark.py --model qwen3-coder:30b --context 131072 --output before.json
python benchmark.py --model qwen3-coder:30b --context 32768 --output after.json
```

The benchmark warms the model, then measures three 256-token-budget generations
and reports median decoding tokens/s, individual samples, load times, and loaded
model placement. A model may stop before the budget. Requests specify context
without changing server configuration; they can reload the model and use GPU
resources. Existing result files are never overwritten. The same prompt is
repeated, so prompt caching may occur: these results measure warm decoding,
not uncached prompt processing or complete Hermes task latency. GPU allocation
and CPU offloading are also reported by setup verification when available.

The existing one-request/one-loaded-model policy prevents concurrent requests
from multiplying context-cache requirements. Q4 cache is not enabled by the
speed preset because it adds a quality tradeoff. A smaller model may be needed
if these models still do not fit in VRAM; no model is silently replaced.
No tokens/s improvement is claimed until measured on the host.

References: [Ollama memory and concurrency settings](https://docs.ollama.com/faq),
[context and offloading](https://docs.ollama.com/context-length), and
[generation timings](https://docs.ollama.com/api/generate).

## Contributors

- **xay-rgp** — Repository author & maintainer
- **Antigravity (Google DeepMind)** — OpenCode setup integration, configuration deployment, and tests
- **Google Gemini** — AI development assistance and co-authorship
