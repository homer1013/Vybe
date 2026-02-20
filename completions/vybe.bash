# bash completion for vybe
_vybe_complete() {
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  local cmds="run r retry rr last l snip s snipclip sc cmdcopy cc tail open o ls ll grep md clip fail errors history select export diff share prompt watch cwd clean stats link flow doctor project proj self-check cfg init completion tags pane man version help"

  if [[ ${COMP_CWORD} -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "${cmds} --help --version -h" -- "${cur}") )
    return 0
  fi

  COMPREPLY=()
  return 0
}
complete -F _vybe_complete vybe
