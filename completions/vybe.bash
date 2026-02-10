# bash completion for vybe
_vybe_complete() {
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  local cmds="run last snip snipclip tail open ls grep md clip fail pane version help"

  if [[ ${COMP_CWORD} -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "${cmds} --help --version -h" -- "${cur}") )
    return 0
  fi

  # minimal: no arg completion beyond command name
  COMPREPLY=()
  return 0
}
complete -F _vybe_complete vybe
