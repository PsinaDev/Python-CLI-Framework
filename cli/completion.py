"""
Shell completion script generation for bash, zsh, and fish.

Generates static completion scripts that enumerate registered commands and
their long options. Subcommand groups (dotted names like ``user.add``) are
flattened to their full name; users can complete by typing the full path.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Shell(str, Enum):
    """Supported shells for completion script generation."""

    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"


def generate_completion(cli: Any, shell: Shell | str) -> str:
    """Return a completion script for the given shell."""
    if isinstance(shell, str):
        try:
            shell = Shell(shell.lower())
        except ValueError:
            valid = ", ".join(s.value for s in Shell)
            raise ValueError(
                f"Unsupported shell '{shell}'. Supported: {valid}"
            )

    program = cli.name
    commands = cli.commands.list_commands()
    options_per_command: dict[str, list[str]] = {}
    for cmd in commands:
        meta = cli.commands.get_command(cmd)
        if not meta:
            continue
        opts: list[str] = []
        for opt in meta.get("options", []):
            opts.append(f"--{opt['name']}")
            if opt.get("default") is True and opt.get("is_flag"):
                opts.append(f"--no-{opt['name']}")
        opts.append("--help")
        options_per_command[cmd] = sorted(set(opts))

    if shell is Shell.BASH:
        return _generate_bash(program, commands, options_per_command)
    if shell is Shell.ZSH:
        return _generate_zsh(program, commands, options_per_command)
    if shell is Shell.FISH:
        return _generate_fish(program, commands, options_per_command)
    raise ValueError(f"Unsupported shell: {shell}")


def _safe_func_name(program: str) -> str:
    return "_" + "".join(c if c.isalnum() else "_" for c in program) + "_complete"


def _generate_bash(
    program: str,
    commands: list[str],
    options_per_command: dict[str, list[str]],
) -> str:
    func = _safe_func_name(program)
    cmd_list = " ".join(commands)
    case_branches: list[str] = []
    for cmd, opts in options_per_command.items():
        case_branches.append(
            f'        {cmd})\n'
            f'            COMPREPLY=( $(compgen -W "{" ".join(opts)}" -- "$cur") )\n'
            f'            return 0\n'
            f'            ;;'
        )
    case_block = "\n".join(case_branches) if case_branches else ""

    return f"""# {program} bash completion
{func}() {{
    local cur prev words cword
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{cmd_list}" -- "$cur") )
        return 0
    fi

    local cmd="${{COMP_WORDS[1]}}"
    case "$cmd" in
{case_block}
        *)
            COMPREPLY=()
            return 0
            ;;
    esac
}}
complete -F {func} {program}
"""


def _generate_zsh(
    program: str,
    commands: list[str],
    options_per_command: dict[str, list[str]],
) -> str:
    func = _safe_func_name(program)
    cmd_descriptions: list[str] = []
    for cmd in commands:
        cmd_descriptions.append(f'"{cmd}:command"')
    cmd_block = " \\\n            ".join(cmd_descriptions)

    case_branches: list[str] = []
    for cmd, opts in options_per_command.items():
        opts_quoted = " ".join(f'"{o}"' for o in opts)
        case_branches.append(
            f"        {cmd})\n"
            f"            _values 'options' {opts_quoted}\n"
            f"            ;;"
        )
    case_block = "\n".join(case_branches) if case_branches else ""

    return f"""#compdef {program}
# {program} zsh completion
{func}() {{
    local context state line
    typeset -A opt_args

    _arguments -C \\
        "1: :->cmd" \\
        "*::arg:->args"

    case $state in
        cmd)
            _values 'commands' \\
            {cmd_block}
            ;;
        args)
            case "$line[1]" in
{case_block}
            esac
            ;;
    esac
}}
{func} "$@"
"""


def _generate_fish(
    program: str,
    commands: list[str],
    options_per_command: dict[str, list[str]],
) -> str:
    lines: list[str] = [f"# {program} fish completion", ""]
    no_command_cond = (
        f"complete -c {program} -n \"not __fish_seen_subcommand_from "
        f"{' '.join(commands)}\" -f"
    )
    for cmd in commands:
        lines.append(f'{no_command_cond} -a "{cmd}"')

    for cmd, opts in options_per_command.items():
        for opt in opts:
            opt_name = opt.lstrip("-")
            lines.append(
                f'complete -c {program} '
                f'-n "__fish_seen_subcommand_from {cmd}" '
                f'-l {opt_name}'
            )

    return "\n".join(lines) + "\n"


__all__ = ["Shell", "generate_completion"]
