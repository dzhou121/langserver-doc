function! langserver_doc#get_context() abort
    let context = {
        \ 'filetype': &filetype,
        \ 'filepath': expand('%:p'),
        \ 'line': line('.') - 1,
        \ 'col': col('.') - 1,
        \ 'mode': mode(),
    \}
    return context
endfunction

function! langserver_doc#request() abort
    let context = langserver_doc#get_context()
    call rpcnotify(g:langserver_doc#channel_id, 'request', context)
endfunction

function! langserver_doc#clear() abort
    call rpcnotify(g:langserver_doc#channel_id, 'clear')
endfunction
