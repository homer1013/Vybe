# fish completion for vybe
complete -c vybe -f
complete -c vybe -n "__fish_use_subcommand" -a "run r retry rr last l snip s snipclip sc cmdcopy cc tail open o ls ll grep md clip fail errors history select export diff share prompt watch cwd clean stats link flow doctor project proj self-check cfg init completion tags pane man version help" -d "Vybe commands"
complete -c vybe -s h -l help -d "Show help"
complete -c vybe -l version -d "Print version"
