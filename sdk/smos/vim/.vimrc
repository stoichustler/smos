" Core buffer and navigation behavior
set autoread
set hidden
set magic
set number
set relativenumber
" Mouse support in normal, visual, insert, and terminal modes
set mouse=a
" Window layout defaults
set nocompatible
set scrolloff=10
set splitbelow
set splitright
" TokyoNight theme; transparent areas inherit terminal opacity
let g:tokyonight_style = 'night' " available: night, storm
let g:tokyonight_enable_italic = 0
let g:tokyonight_transparent_background = 1
set termguicolors
set background=dark
colorscheme tokyonight
" Text encoding
set encoding=utf-8
set termencoding=utf-8
" Filetype-aware indentation with a four-space global fallback
set autoindent
filetype plugin indent on

" Default indentation for filetypes without a dedicated profile
set tabstop=4
set shiftwidth=4
set softtabstop=4
set expandtab

" C/C++ profiles apply only to the current buffer.
" Run gg=G after selecting a profile to reindent existing code.
function! s:ApplyCStyle(style) abort
    setlocal autoindent cindent nosmartindent
    setlocal nocopyindent nopreserveindent

    if a:style ==# 'hypervisor'
        setlocal tabstop=8 shiftwidth=8 softtabstop=8 noexpandtab
        setlocal cinoptions=:0,l1,g4,h4,N0,t0,+8,(8,W8
        let l:name = 'Hypervisor/BEAU (tabs 8)'
    elseif a:style ==# 'google'
        setlocal tabstop=2 shiftwidth=2 softtabstop=2 expandtab
        setlocal cinoptions=:s,l1,g1,h1,N-s,t0,+4,(4,W4
        let l:name = 'Google C++ (spaces 2)'
    elseif a:style ==# 'linux'
        setlocal tabstop=8 shiftwidth=8 softtabstop=8 noexpandtab
        setlocal cinoptions=:0,l1,g0,h8,N0,t0,+8,(0,w1,W8
        let l:name = 'Linux kernel (tabs 8)'
    else
        echoerr 'Unknown C/C++ style: ' . a:style
        return
    endif

    let b:beau_c_style = a:style
    echo 'C/C++ style: ' . l:name
endfunction

command! BEAUStyle call <SID>ApplyCStyle('hypervisor')
command! GOOGLEStyle call <SID>ApplyCStyle('google')
command! LINUXStyle call <SID>ApplyCStyle('linux')

" System clipboard integration
set clipboard=unnamedplus
nnoremap <silent> <C-c> "+y
vnoremap <silent> <C-c> "+y
" Confirm destructive operations instead of failing immediately
set confirm
set linespace=0
" Render tabs, trailing spaces, and off-screen overflow markers
set list
set listchars=tab:·\ ,trail:·,precedes:←,extends:→
" Soft wrapping for long lines
set wrap
set linebreak
set breakindent
set breakindentopt=shift:2
" Command feedback, searching, and status display
set laststatus=2
set cmdheight=1
set noshowmode
set showcmd
set showcmdloc=statusline
set noruler
set hlsearch
set incsearch
set ignorecase
set smartcase
set matchtime=1
set nobackup
" Keep recovery and persistent undo files out of project directories
let s:swap_dir = expand('~/.vim/swap')
let s:undo_dir = expand('~/.vim/undo')
call mkdir(s:swap_dir, 'p', 0700)
call mkdir(s:undo_dir, 'p', 0700)
let &directory = s:swap_dir . '//'
let &undodir = s:undo_dir . '//'
set swapfile
set undofile
set guioptions-=T
set guioptions-=m
set report=0
set cursorline
" Popup completion for Ex commands and insert-mode completion
set wildmenu
set wildmode=full
set wildoptions=pum
set completeopt=menu,preview,longest
set previewpopup=height:20,width:80
" Hide the default split separator for a cleaner layout
set fillchars=vert:\ ,
" Allow Backspace across indentation, line breaks, and insert start
set backspace=2
syntax on
" Search tags upward from the current file's directory
set tags=tags;
" Custom statusline: mode, file state, command keys, type, and position
function! BeauStatusMode() abort
    let l:mode = mode(1)
    if l:mode =~# '^n'
        return 'NORMAL'
    elseif l:mode =~# '^i'
        return 'INSERT'
    elseif l:mode =~# '^R'
        return 'REPLACE'
    elseif l:mode ==# 'v'
        return 'VISUAL'
    elseif l:mode ==# 'V'
        return 'V-LINE'
    elseif l:mode ==# "\<C-v>"
        return 'V-BLOCK'
    elseif l:mode =~# '^c'
        return 'COMMAND'
    elseif l:mode =~# '^t'
        return 'TERMINAL'
    endif
    return toupper(l:mode)
endfunction

function! s:ApplyStatuslineColors() abort
    highlight BeauStatusMode cterm=bold ctermfg=0 ctermbg=12
        \ gui=bold guifg=#1a1b26 guibg=#7aa2f7
    highlight BeauStatusFile cterm=NONE ctermfg=15 ctermbg=8
        \ gui=NONE guifg=#c0caf5 guibg=#32344a
    highlight BeauStatusMeta cterm=NONE ctermfg=7 ctermbg=0
        \ gui=NONE guifg=#a9b1d6 guibg=#2a2b3d
endfunction

call s:ApplyStatuslineColors()

augroup beau_statusline_colors
    autocmd!
    autocmd ColorScheme * call <SID>ApplyStatuslineColors()
augroup END

set statusline=
let &statusline .= '%#BeauStatusMode# BEAU:%{BeauStatusMode()} '
set statusline+=%#BeauStatusFile#\ %F%<
set statusline+=\ %h%m%r%w\ %S
set statusline+=%=
let &statusline .= '%#BeauStatusMeta# %y %l:%c %p%% '

if exists('s:statusline_timer')
    call timer_stop(s:statusline_timer)
    unlet s:statusline_timer
endif

" Style the native ':' command line as a thin bottom command panel
let s:cmdline_msgarea = []
let s:cmdline_showcmd = &showcmd

function! s:CmdlineUiEnter() abort
    let s:cmdline_msgarea = hlget('MsgArea')
    let s:cmdline_showcmd = &showcmd
    set noshowcmd
    call hlset([{'name': 'MsgArea', 'linksto': 'Pmenu'}])
    redraw
endfunction

function! s:CmdlineUiLeave() abort
    if !empty(s:cmdline_msgarea)
        call hlset(s:cmdline_msgarea)
    endif
    let &showcmd = s:cmdline_showcmd
    redraw
endfunction

augroup beau_cmdline_ui
    autocmd!
    autocmd CmdlineEnter : call <SID>CmdlineUiEnter()
    autocmd CmdlineLeave : call <SID>CmdlineUiLeave()
augroup END

" Reusable floating shell; hiding it preserves the process and cwd
if !exists('s:floating_terminal')
    let s:floating_terminal = {'buf': -1, 'win': -1}
endif

function! s:ApplyFloatingTerminalColors() abort
    highlight BeauTerminal ctermfg=15 ctermbg=NONE
        \ guifg=#c0caf5 guibg=NONE
    highlight BeauTerminalBorder cterm=bold ctermfg=12 ctermbg=NONE
        \ gui=bold guifg=#7aa2f7 guibg=NONE
endfunction

function! s:FloatingTerminalSize() abort
    let l:width = max([20, min([float2nr(&columns * 0.85), &columns - 4])])
    let l:height = max([5, min([float2nr((&lines - 2) * 0.70), &lines - 4])])
    return {
        \ 'minwidth': l:width,
        \ 'maxwidth': l:width,
        \ 'minheight': l:height,
        \ 'maxheight': l:height
        \ }
endfunction

function! s:FloatingTerminalVisible() abort
    if s:floating_terminal.win <= 0
        return 0
    endif
    let l:pos = popup_getpos(s:floating_terminal.win)
    return !empty(l:pos) && get(l:pos, 'visible', 0)
endfunction

function! s:FloatingTerminalAlive() abort
    if s:floating_terminal.buf <= 0
        \ || !bufexists(s:floating_terminal.buf)
        return 0
    endif
    try
        return job_status(term_getjob(s:floating_terminal.buf)) ==# 'run'
    catch
        return 0
    endtry
endfunction

function! s:FloatingTerminalClosed(id, result) abort
    if s:floating_terminal.win == a:id
        let s:floating_terminal.win = -1
    endif
endfunction

function! s:CloseFloatingTerminal() abort
    let l:buf = s:floating_terminal.buf
    let l:win = s:floating_terminal.win
    let s:floating_terminal = {'buf': -1, 'win': -1}

    if l:win > 0 && !empty(popup_getpos(l:win))
        call popup_close(l:win)
    endif
    if l:buf > 0 && bufexists(l:buf)
        execute 'silent! bwipeout! ' . l:buf
    endif
endfunction

function! s:ResizeFloatingTerminal() abort
    if s:FloatingTerminalVisible()
        call popup_setoptions(
            \ s:floating_terminal.win, s:FloatingTerminalSize())
    endif
endfunction

function! s:EnsureFloatingTerminalJobMode(timer) abort
    if s:FloatingTerminalVisible() && mode(1) !~# '^t'
        call feedkeys('i', 'n')
    endif
endfunction

function! s:ConfigureFloatingTerminalKeys() abort
    " Double Esc closes the shell; Ctrl-Q only hides it for later reuse.
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <Esc><Esc> '
        \ . '<C-\><C-N><Cmd>FloatTerminalClose<CR>')
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <C-q> '
        \ . '<C-\><C-N><Cmd>FloatTerminal<CR>')
endfunction

function! s:ToggleFloatingTerminal() abort
    if s:FloatingTerminalVisible()
        call popup_close(s:floating_terminal.win)
        let s:floating_terminal.win = -1
        return
    endif

    let l:size = s:FloatingTerminalSize()
    if !s:FloatingTerminalAlive()
        if s:floating_terminal.buf > 0
            \ && bufexists(s:floating_terminal.buf)
            execute 'silent! bwipeout! ' . s:floating_terminal.buf
        endif
        let s:floating_terminal.buf = term_start(&shell, {
            \ 'hidden': 1,
            \ 'term_finish': 'close',
            \ 'term_name': 'BEAU Terminal',
            \ 'term_highlight': 'BeauTerminal',
            \ 'term_rows': l:size.minheight,
            \ 'term_cols': l:size.minwidth
            \ })
        if s:floating_terminal.buf <= 0
            echoerr 'Unable to start floating terminal'
            return
        endif
        call setbufvar(s:floating_terminal.buf, '&bufhidden', 'hide')
        call term_setkill(s:floating_terminal.buf, 'kill')
    endif

    let l:options = extend(l:size, {
        \ 'pos': 'center',
        \ 'border': [1, 1, 1, 1],
        \ 'padding': [0, 1, 0, 1],
        \ 'title': ' BEAU Terminal ',
        \ 'close': 'button',
        \ 'drag': 1,
        \ 'resize': 1,
        \ 'highlight': 'BeauTerminal',
        \ 'borderhighlight': ['BeauTerminalBorder'],
        \ 'callback': function('<SID>FloatingTerminalClosed')
        \ })
    try
        let s:floating_terminal.win = popup_create(
            \ s:floating_terminal.buf, l:options)
        call s:ConfigureFloatingTerminalKeys()
        call timer_start(0, function('<SID>EnsureFloatingTerminalJobMode'))
    catch
        let s:floating_terminal.win = -1
        echohl ErrorMsg
        echomsg substitute(v:exception, '^Vim\%((\a\+)\)\=:', '', '')
        echohl None
    endtry
endfunction

call s:ApplyFloatingTerminalColors()
command! FloatTerminal call <SID>ToggleFloatingTerminal()
command! FloatTerminalClose call <SID>CloseFloatingTerminal()

augroup beau_floating_terminal
    autocmd!
    autocmd ColorScheme * call <SID>ApplyFloatingTerminalColors()
    autocmd VimResized * call <SID>ResizeFloatingTerminal()
augroup END

" fzf.vim popup and preview layout
set rtp+=~/.fzf

let g:fzf_layout = {
    \ 'window': {
    \   'width': 0.92,
    \   'height': 0.85,
    \   'highlight': 'Normal',
    \   'border': 'rounded'
    \ }
    \ }
let g:fzf_vim = {}
let g:fzf_vim.preview_window = ['right,55%,<100(up,45%)', 'ctrl-/']
let g:fzf_vim.buffers_jump = 1

function! s:ConfigureFzfTerminalKeys() abort
    " Keep repeated Esc inside fzf instead of entering Terminal-Normal mode.
    tnoremap <silent> <buffer> <Esc><Esc> <Esc>
    tnoremap <silent> <buffer> :q<CR> <Esc>
endfunction

augroup beau_fzf_terminal_keys
    autocmd!
    autocmd FileType fzf call <SID>ConfigureFzfTerminalKeys()
augroup END

let s:rg_history = {
    \ 'text': expand('~/.vim/rg-history'),
    \ 'regex': expand('~/.vim/rg-regex-history')
    \ }

" All Rg variants stay anchored to the directory where Vim started.
if !exists('g:beau_workspace_root')
    let g:beau_workspace_root = getcwd()
endif

function! s:LiveRg(query, fullscreen, regex) abort
    if !executable('rg')
        echoerr 'Rg requires ripgrep (rg) in PATH'
        return
    endif

    let l:root = g:beau_workspace_root
    let l:flags = '--column --line-number --no-heading --color=always '
        \ . '--smart-case --hidden --glob ' . shellescape('!.git/*')
    if !a:regex
        let l:flags .= ' --fixed-strings'
    endif

    " Do not scan the entire workspace before the first character is typed.
    let l:script = 'test -z "$1" || exec rg ' . l:flags . ' -- "$1"'
    let l:prefix = 'sh -c ' . shellescape(l:script) . ' sh'
    let l:mode = a:regex ? 'Regex' : 'Text'
    let l:history = a:regex ? s:rg_history.regex : s:rg_history.text
    let l:options = [
        \ '--layout=reverse',
        \ '--info=inline-right',
        \ '--history', l:history,
        \ '--prompt', 'Search (' . l:mode . ')> ',
        \ '--header', 'Workspace: ' . l:root
        \   . '  |  CTRL-/ preview  CTRL-X/V/T split/vsplit/tab'
        \ ]
    let l:spec = fzf#vim#with_preview({
        \ 'dir': l:root,
        \ 'options': l:options
        \ })
    call fzf#vim#grep2(l:prefix, a:query, l:spec, a:fullscreen)
endfunction

function! s:LiveRgWord() abort
    let l:query = expand('<cword>')
    " Ignore punctuation-only words from filetype-specific iskeyword values.
    if l:query !~# '[[:alnum:]_]'
        let l:query = ''
    endif
    call s:LiveRg(l:query, 0, 0)
endfunction

function! s:LiveRgVisual() abort
    let l:saved = [getreg('z'), getregtype('z')]
    silent normal! gv"zy
    let l:query = trim(substitute(getreg('z'), '\r\?\n', ' ', 'g'))
    call setreg('z', l:saved[0], l:saved[1])
    call s:LiveRg(l:query, 0, 0)
endfunction

function! s:DefineRgCommands() abort
    command! -bang -nargs=* Rg
        \ call <SID>LiveRg(<q-args>, <bang>0, 0)
    command! -bang -nargs=* RgRegex
        \ call <SID>LiveRg(<q-args>, <bang>0, 1)
endfunction

" Recreate commands safely when reloading ~/.vimrc.
call s:DefineRgCommands()

" Space is the leader for project-style commands
let mapleader=' '
set timeoutlen=400

" NERDTree file explorer; never change Vim's working directory
let g:NERDTreeWinSize = 35
let g:NERDTreeWinSizeMax = 40
let g:NERDTreeShowHidden = 1
let g:NERDTreeAutoCenter = 1
let g:NERDTreeChDirMode = 0
" netrw fallback file explorer
let g:netrw_winsize   = 20
let g:netrw_liststyle = 3
let g:netrw_hide      = 1
let g:netrw_banner    = 0
let g:netrw_keepdir   = 1
let g:netrw_sort_by   = "name"
" Paste directly from the system clipboard
nnoremap <silent> <C-p> "+p
" File explorer and workspace search
nnoremap <silent> <Leader>e :NERDTreeToggle<CR>
nnoremap <silent> <Leader>f <Nop>
xnoremap <silent> <Leader>f <Nop>
nnoremap <silent> <Leader>fe :FZF<CR>
nnoremap <silent> <Leader>fg :Rg<CR>
nnoremap <silent> <Leader>fw :call <SID>LiveRgWord()<CR>
xnoremap <silent> <Leader>fg :<C-u>call <SID>LiveRgVisual()<CR>
nnoremap <silent> <Leader>re :RgRegex<CR>
" Floating terminal and window switching
nnoremap <silent> <Leader>t <Cmd>FloatTerminal<CR>
nnoremap <silent> <Leader>w <C-w><C-w>
" Ctags: Ctrl-] jumps directly; Space-g opens candidates with preview.
function! s:FzfTagUnderCursor() abort
    let l:symbol = expand('<cword>')
    if empty(l:symbol)
        echo 'No symbol under cursor'
        return
    endif
    call fzf#vim#tags(l:symbol, fzf#vim#with_preview({
        \ 'placeholder': '--tag {2}:{-1}:{3..}'
        \ }), 0)
endfunction

nnoremap <silent> <Leader>g <Cmd>call <SID>FzfTagUnderCursor()<CR>
" Navigation back works for FZF, searches, and native tag jumps.
nnoremap <silent> <Leader>b <C-o>
" Paragraph navigation
nnoremap <silent> <Leader>d }
nnoremap <silent> <Leader>u {
" Toggle between a clean presentation view and the editing view
nnoremap <silent> <Leader>n
    \ :set nonu<CR>:set mouse=<CR>:set norelativenumber<CR>
    \ :set nolist<CR>
nnoremap <silent> <Leader>m
    \ :set nu<CR>:set mouse=a<CR>:set relativenumber<CR>
    \ :set list<CR>
" Insert completion uses Vim's built-in Ctrl-N and Ctrl-P.
