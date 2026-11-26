#!/usr/bin/env python3
"""Merge local-model configuration into Hermes and OpenCode; preserve unrelated settings."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import urllib.request
import urllib.error

try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML is required. Install python-yaml on Arch before configuring.')


def read_json(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return data


def save(path, text):
    """Back up changed files, then replace atomically; unchanged files stay alone."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'Refusing to replace symlink {path}; edit its target manually')
    if path.exists() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if path.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path, path.with_name(path.name + '.backup-' + stamp))
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Updated {path}')


CONTINUITY_INSTRUCTIONS = '''Conversation continuity:
- Proactively use the memory tool to save durable user preferences, project facts, decisions, and useful outcomes. Save concise entries as they become clear; do not wait for the user to say "remember". Never save passwords, tokens, or other secrets.
- When the user refers to earlier conversations or ongoing work, use session_search to retrieve relevant past messages before answering. If the topic is unclear, browse recent sessions first. Do not claim you cannot remember until you have checked saved memory and session history.
- Only say a fact was saved after the memory tool confirms success. Keep memories compact and current, and distinguish retrieved facts from guesses.
'''


def memory_files(hermes_home, memory):
    """Prepare continuity instructions and initial notes without replacing memories."""
    soul = hermes_home / 'SOUL.md'
    existing = soul.read_text() if soul.exists() else ''
    pending = {}
    if CONTINUITY_INSTRUCTIONS.strip() not in existing:
        pending[soul] = existing.rstrip() + ('\n\n' if existing.strip() else '') + CONTINUITY_INSTRUCTIONS
    seeds = {
        'USER.md': 'User wants Hermes to remember previous conversations and maintain continuity across sessions. Proactively retain useful preferences and project decisions, and recall relevant earlier chats when needed.\n',
        'MEMORY.md': f'Hermes home is {hermes_home}. Prior conversations are stored in state.db and can be retrieved with session_search. Persistent notes are in memories/MEMORY.md and memories/USER.md.\n',
    }
    for name, text in seeds.items():
        path = hermes_home / 'memories' / name
        if path.is_symlink():
            raise ValueError(f'Refusing to replace symlink {path}; edit its target manually')
        if path.exists() and not path.is_file():
            raise ValueError(f'{path} must be a regular file')
        if not path.exists():
            key, default = ('memory_char_limit', 2200) if name == 'MEMORY.md' else ('user_char_limit', 1375)
            limit = int(memory.get(key, default))
            # Do not seed beyond a user's existing capacity. SOUL.md still
            # supplies recall instructions when a store is too small for a seed.
            pending[path] = text if len(text) <= limit else ''
    return pending


def opencode_files(home, ordered_models, context):
    """Prepare OpenCode config, CLI theme/plugins, and bundled skills without touching secrets or memories."""
    template_dir = Path(__file__).resolve().parent / 'opencode'
    opencode_dir = home / '.config/opencode'
    pending = {}

    oc_path = opencode_dir / 'opencode.json'
    oc_template = read_json(template_dir / 'opencode.json')
    oc_cfg = read_json(oc_path)
    for key in ('$schema', 'model', 'small_model', 'compaction'):
        if key in oc_template:
            oc_cfg[key] = oc_template[key]
    provider = oc_cfg.get('provider', {})
    if not isinstance(provider, dict):
        raise ValueError(f'{oc_path}: provider must be an object')
    provider = dict(provider)
    ollama_provider = provider.get('ollama', {})
    if not isinstance(ollama_provider, dict):
        raise ValueError(f'{oc_path}: provider.ollama must be an object')
    ollama_provider = dict(ollama_provider)
    ollama_models = ollama_provider.get('models', {})
    if not isinstance(ollama_models, dict):
        raise ValueError(f'{oc_path}: provider.ollama.models must be an object')
    ollama_models = dict(ollama_models)
    default_output = min(16384, context)
    for name in ordered_models:
        existing_entry = ollama_models.get(name, {})
        if not isinstance(existing_entry, dict):
            existing_entry = {}
        existing_limit = existing_entry.get('limit', {})
        if not isinstance(existing_limit, dict):
            existing_limit = {}
        ollama_models[name] = {
            **existing_entry,
            'limit': {
                **existing_limit,
                'context': context,
                'output': existing_limit.get('output', default_output),
            },
        }
    ollama_provider['models'] = ollama_models
    provider['ollama'] = ollama_provider
    oc_cfg['provider'] = provider
    pending[oc_path] = json.dumps(oc_cfg, indent=2) + '\n'

    cli_path = opencode_dir / 'cli.json'
    cli_template = read_json(template_dir / 'cli.json')
    cli_cfg = read_json(cli_path)
    for key in ('$schema', 'theme'):
        if key in cli_template:
            cli_cfg[key] = cli_template[key]
    existing_plugins = cli_cfg.get('plugins', [])
    if not isinstance(existing_plugins, list):
        raise ValueError(f'{cli_path}: plugins must be a list')
    template_plugins = cli_template.get('plugins', [])
    cli_cfg['plugins'] = list(dict.fromkeys(list(existing_plugins) + list(template_plugins)))
    pending[cli_path] = json.dumps(cli_cfg, indent=2) + '\n'

    skills_src = template_dir / 'skills'
    if skills_src.is_dir():
        for src in sorted(skills_src.rglob('*')):
            if src.is_file():
                rel = src.relative_to(skills_src)
                pending[opencode_dir / 'skills' / rel] = src.read_text(encoding='utf-8')

    return pending


def configure(home, models, default, context=65536, hermes_home=None, check_only=False):
    if not models or len(set(models)) != len(models) or default not in models:
        raise ValueError('Models must be unique and include the default')
    if context <= 0:
        raise ValueError('Context length must be positive')
    hermes_home = hermes_home if hermes_home is not None else home / '.hermes'
    ollama_path = home / '.ollama/config.json'
    hermes_path = hermes_home / 'config.yaml'
    # Parse and validate both files before making any writes.
    ollama = read_json(ollama_path)
    hermes = yaml.safe_load(hermes_path.read_text()) if hermes_path.exists() else {}
    if hermes is None:
        hermes = {}
    if not isinstance(hermes, dict):
        raise ValueError(f'{hermes_path} must contain a YAML mapping')
    model = hermes.get('model', {})
    # Hermes also accepts a bare model name in older configurations.
    if isinstance(model, str):
        model = {'default': model}
    if not isinstance(model, dict):
        raise ValueError(f'{hermes_path}: model must be a mapping or string')
    # YAML aliases can share this mapping with auxiliary/provider settings.
    model = dict(model)
    model.update({'default': default, 'provider': 'custom',
                  'base_url': 'http://127.0.0.1:11434/v1',
                  'api_key': 'ollama', 'api_mode': 'chat_completions',
                  'context_length': context})
    hermes['model'] = model
    display = hermes.get('display', {})
    if not isinstance(display, dict):
        raise ValueError(f'{hermes_path}: display must be a mapping')
    hermes['display'] = {**display, 'skin': 'white'}
    memory = hermes.get('memory', {})
    if not isinstance(memory, dict):
        raise ValueError(f'{hermes_path}: memory must be a mapping')
    hermes['memory'] = {**memory, 'memory_enabled': True, 'user_profile_enabled': True}
    white_skin = (Path(__file__).resolve().parent / 'skins/white.yaml').read_text()
    integrations = ollama.setdefault('integrations', {})
    if not isinstance(integrations, dict):
        raise ValueError(f'{ollama_path}: integrations must be an object')
    if not isinstance(integrations.get('hermes', {}), dict):
        raise ValueError(f'{ollama_path}: integrations.hermes must be an object')
    ordered = [default] + [name for name in models if name != default]
    integrations.setdefault('hermes', {})['models'] = ordered
    providers = hermes.get('custom_providers', [])
    if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
        raise ValueError(f'{hermes_path}: custom_providers must be a list of mappings')
    providers = [dict(p) for p in providers]
    local = next((p for p in providers if p.get('name') == 'Local Ollama'
                  and p.get('base_url', '').rstrip('/') == model['base_url']), None)
    if local is None:
        local = {'name': 'Local Ollama'}
        providers.append(local)
    local.update({'base_url': model['base_url'], 'api_key': 'ollama',
                  'api_mode': 'chat_completions', 'model': default,
                  'models': {name: {'context_length': context} for name in ordered}})
    hermes['custom_providers'] = providers
    pending = {hermes_home / 'skins/white.yaml': white_skin,
               ollama_path: json.dumps(ollama, indent=2) + '\n',
               hermes_path: yaml.safe_dump(hermes, sort_keys=False, allow_unicode=True)}
    pending.update(memory_files(hermes_home, memory))
    pending.update(opencode_files(home, ordered, context))

    # Avoid global API environment exports; configure each agent explicitly.
    path_script = '''# Managed by LocalModelSetupScript. Bash login/interactive PATH.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
'''
    pending[home / '.config/local-model-setup/path.sh'] = path_script
    source_line = '[ ! -f "$HOME/.config/local-model-setup/path.sh" ] || . "$HOME/.config/local-model-setup/path.sh"'
    for name in ['.bashrc', '.bash_profile']:
        path = home / name
        existing = path.read_text() if path.exists() else ''
        # Preserve Bash's login-file precedence when introducing .bash_profile.
        if name == '.bash_profile' and not path.exists():
            existing = ('if [ -f "$HOME/.bash_login" ]; then\n'
                        '  . "$HOME/.bash_login"\n'
                        'elif [ -f "$HOME/.profile" ]; then\n'
                        '  . "$HOME/.profile"\n'
                        'fi\n')
            existing += '[ ! -f "$HOME/.bashrc" ] || . "$HOME/.bashrc"\n'
        if source_line not in existing.splitlines():
            pending[path] = existing.rstrip('\n') + '\n\n# Local model agents\n' + source_line + '\n'
    pending[home / '.config/fish/conf.d/local-model-setup.fish'] = (
         '# Managed by LocalModelSetupScript.\n'
         'fish_add_path --path "$HOME/.local/bin"\n')

    # Validate the complete output set before touching any files.
    for path in pending:
        if path.is_symlink():
            raise ValueError(f'Refusing to replace symlink {path}; edit its target manually')
        if path.exists() and not path.is_file():
            raise ValueError(f'{path} must be a regular file')
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                raise ValueError(f'{parent} must be a directory')
    if not check_only:
        for path, text in pending.items():
            save(path, text)
        # Clear Hermes's cached Ollama /api/show probes so updated num_ctx takes effect immediately.
        probe_cache = hermes_home / 'cache/local_endpoint_probes.json'
        if probe_cache.is_file() and not probe_cache.is_symlink():
            probe_cache.unlink(missing_ok=True)


def installed_models():
    """Read the local server catalog; fall back to Arch's on-disk catalog."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:11434/api/tags', timeout=5) as response:
            catalog = json.load(response)
        if not isinstance(catalog, dict) or not isinstance(catalog.get('models'), list):
            raise ValueError('Invalid Ollama model catalog')
        if any(not isinstance(m, dict) for m in catalog['models']):
            raise ValueError('Invalid Ollama model entry')
        return list(dict.fromkeys(
            m['name'] for m in catalog['models']
            if isinstance(m.get('name'), str) and m['name'].strip()
            and not m['name'].endswith(':cloud')
            and not m.get('remote_host') and not m.get('remote_model')))
    except (OSError, ValueError, urllib.error.URLError):
        roots = [Path(os.environ.get('OLLAMA_MODELS', '/var/lib/ollama')),
                 Path.home() / '.ollama/models']
        names = []
        for root in roots:
            manifests = root / 'manifests'
            for path in sorted(manifests.glob('*/*/*/*')):
                if not path.is_file():
                    continue
                registry, namespace, model, tag = path.relative_to(manifests).parts
                if tag == 'cloud':
                    continue
                name = ('' if namespace == 'library' else namespace + '/') + model + ':' + tag
                if registry != 'registry.ollama.ai':
                    name = registry + '/' + name
                names.append(name)
        return list(dict.fromkeys(names))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--default', required=True)
    parser.add_argument('--context', type=int, default=65536)
    parser.add_argument('--hermes-home', type=Path)
    parser.add_argument('--discover-installed', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.discover_installed:
        args.models = list(dict.fromkeys(args.models + installed_models()))
    configure(args.home, args.models, args.default, args.context, args.hermes_home, args.check_only)


if __name__ == '__main__':
    main()
