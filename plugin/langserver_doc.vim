function! s:is_initialized() abort "{{{
  return exists('g:langserver_doc#channel_id')
endfunction"}}}

function! langserver_doc#init() abort "{{{
  if s:is_initialized()
    return
  endif
  if !exists('g:loaded_remote_plugins')
    runtime! plugin/rplugin.vim
  endif
  call _langserver_doc()
endfunction"}}}

call langserver_doc#init()

autocmd CursorMovedI * call langserver_doc#request()
autocmd InsertEnter * call langserver_doc#request()
autocmd InsertLeave * call langserver_doc#clear()
