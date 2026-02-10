# fish completion for vybe
complete -c vybe -f
complete -c vybe -n "__fish_use_subcommand" -a "run last snip snipclip tail open ls grep md clip fail pane version help" -d "Vybe commands"
complete -c vybe -s h -l help -d "Show help"
complete -c vybe -l version -d "Print version"
