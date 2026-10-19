" BEAU / SMOS host Vimrc (not shipped in the target image).
"
" Source of truth: sdk/smos/vim/.vimrc
" Install:         install -Dm644 sdk/smos/vim/.vimrc ~/.vimrc
" Reload:          :source $MYVIMRC
" Related notes:   sdk/smos/vim/vim.md
"
" This file is reload-safe: jobs, timers, and popups from a previous
" :source are stopped before their script-local state is recreated.
"
" Contents
"   1. Startup, leader, runtime packs
"   2. Core buffer / window options
"   3. Colorscheme
"   4. Indentation and C/C++ style commands
"   5. File defaults (formatprg, last-position, autoread)
"   6. Clipboard (X11/Wayland, OSC 52, W23)
"   7. Display, search, swap/undo, completion
"   8. Statusline and async git branch
"   9. Command-line UI
"  10. Floating terminal
"  11. fzf / live ripgrep
"  12. Git signs
"  13. Plugin knobs (NERDTree, netrw, Tagbar, NERDCommenter)
"  14. Commands and Space-leader maps
"
" Compatibility and encoding must come first; nocompatible can reset options.
set nocompatible
set encoding=utf-8
scriptencoding utf-8

" Space is the leader for project-style commands.
" Map Space to <Nop> so a lone Space does not move the cursor while waiting
" for timeoutlen (600 ms) to decide whether a leader sequence follows.
let mapleader = ' '
let maplocalleader = '\'
nnoremap <Space> <Nop>
xnoremap <Space> <Nop>

" Bundled optional packs from the Vim runtime, not third-party plugins.
packadd! matchit        " % matches if/endif, HTML tags, etc.
packadd! editorconfig   " per-project indent from .editorconfig
packadd! hlyank         " brief highlight after yank
packadd! cfilter        " :Cfilter / :Lfilter on quickfix/location lists

" Core buffer and navigation behavior
set autoread
set hidden
set magic
set number
set relativenumber
" Mouse support in normal, visual, insert, and terminal modes.
" SGR is needed for columns beyond 223 in modern terminals.
set mouse=a
if has('mouse_sgr')
    set ttymouse=sgr
endif
set scrolloff=10
set splitbelow
set splitright
set smoothscroll
set splitkeep=screen
set confirm
set belloff=all
set history=1000
set undolevels=5000
set nrformats-=octal
set display+=lastline
set switchbuf=useopen,usetab
set updatetime=400
" timeoutlen: mapped key sequences (leader maps). ttimeoutlen: Esc / keycodes.
set timeout
set ttimeout
set timeoutlen=600
set ttimeoutlen=20

" --- Colorscheme -------------------------------------------------------------
" TokyoNight theme; transparent areas inherit terminal opacity.
" Apply the colorscheme after syntax so highlight groups are not reset.
let g:tokyonight_style = 'storm' " available: night, storm
let g:tokyonight_enable_italic = 0
let g:tokyonight_transparent_background = 1
filetype plugin indent on
syntax on
set termguicolors
set background=dark
try
    colorscheme tokyonight
catch
    silent! colorscheme default
endtry

" --- Indentation -------------------------------------------------------------
" Filetype-aware indentation with a four-space global fallback.
set autoindent
set tabstop=4
set shiftwidth=4
set softtabstop=4
set expandtab
set shiftround

" --- C/C++ indent profiles ---------------------------------------------------
" Buffer-local only. :BEAUStyle / :GOOGLEStyle / :LINUXStyle.
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

" --- File defaults -----------------------------------------------------------
" formatprg feeds :Format / Space-=. Last-position restore skips special
" buffers. checktime implements autoread when focus returns.
augroup beau_file_defaults
    autocmd!
    autocmd FileType c,cpp,objc,objcpp
        \ if executable('clang-format') |
        \     setlocal formatprg=clang-format |
        \ endif
    autocmd FileType rust
        \ if executable('rustfmt') |
        \     setlocal formatprg=rustfmt |
        \ endif
    autocmd BufReadPost *
        \ if line("'\"") > 0 && line("'\"") <= line('$') && &buftype ==# '' |
        \     execute 'normal! g`"' |
        \ endif
    autocmd FocusGained,BufEnter * silent! checktime
augroup END

" --- Clipboard ---------------------------------------------------------------
" System clipboard. Prefer X11/Wayland when a display exists.
" Over SSH/tty, force OSC 52 before unnamedplus so yank does not emit W23.
" Skip OSC 52 on linux/cons/dumb/vt terminals to avoid escape garbage.
" Disable OSC paste so a terminal without it cannot block on paste.
if has('clipboard_provider') && exists('+clipmethod')
    let g:osc52_disable_paste = 1
    try
        " No native display: do not wait for DA1 (unreliable over SSH/tmux).
        " Skip linux/cons/dumb/vt so OSC 52 escapes are not printed as text.
        if empty($DISPLAY) && empty($WAYLAND_DISPLAY)
            \ && &term !~? '^\%(linux\|cons\|dumb\|vt\)'
            let g:osc52_force_avail = 1
            packadd osc52
            set clipmethod=osc52
        else
            packadd osc52
            if &clipmethod !~# '\<osc52\>'
                let &clipmethod .= (empty(&clipmethod) ? '' : ',') . 'osc52'
            endif
        endif
    catch
    endtry
endif
" unnamedplus maps yank/delete to + and emits W23 when v:clipmethod is none.
if exists('v:clipmethod') && v:clipmethod !=# 'none'
    set clipboard=unnamedplus
endif
set linespace=0

" --- Display, search, files --------------------------------------------------
" Render tabs, trailing spaces, and off-screen overflow markers
set list
set listchars=tab:·\ ,trail:·,nbsp:␣,precedes:←,extends:→
" Soft wrapping for long lines
set wrap
set linebreak
set breakindent
set breakindentopt=shift:2
" Command feedback, searching, and status display.
" noshowmode/noruler: the custom statusline already shows mode and position.
" showcmdloc=statusline: pending operator keys appear in %S, not the cmdline.
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
set infercase
set matchtime=1
set nobackup
set shortmess+=c
set formatoptions+=j
set synmaxcol=1000
" Swap/undo live under ~/.vim so :e in a source tree does not drop .swp files.
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
" Popup completion for Ex commands and file paths (for example, :write)
set wildmenu
set wildmode=longest:full,full
set wildoptions=pum,fuzzy
set wildignorecase
set wildignore+=*/.git/*,*/.hg/*,*/.svn/*
set wildignore+=*/out/*,*/build/*,*/target/*,*/node_modules/*
set wildignore+=*.o,*.obj,*.a,*.so,*.pyc,*.class,*.swp,*.bin
set wildignore+=tags,TAGS,GTAGS,GRTAGS,GPATH,cscope.out
set completeopt=menuone,popup,fuzzy
set completepopup=height:12,width:70,border:round,highlight:Pmenu
set previewpopup=height:20,width:80
" Hide the default split separator for a cleaner layout
let &fillchars = 'vert: ,eob: '
set diffopt=internal,filler,closeoff,hiddenoff,algorithm:histogram,indent-heuristic,linematch:60
set backspace=indent,eol,start
" Search tags from the current file upward, then from the working directory.
set tags=./tags;,tags

" :grep and fzf file listing share the same hidden-but-not-.git rg flags.
if executable('rg')
    let &grepprg = "rg --vimgrep --smart-case --hidden --glob '!.git/*'"
    set grepformat=%f:%l:%c:%m
    if empty($FZF_DEFAULT_COMMAND)
        let $FZF_DEFAULT_COMMAND = 'rg --files --hidden --glob "!.git/*"'
    endif
endif

let g:hlyank_hlgroup = 'IncSearch'
let g:hlyank_duration = 250
let g:EditorConfig_exclude_patterns = ['fugitive://.*', 'scp://.*']

" --- Statusline --------------------------------------------------------------
" Layout: BEAU:<mode>  <path>  [branch]  flags  %S  |  <ft> <pos>
" BeauStatusMode/BeauGitBranch are global so %{...} in 'statusline' can call them.
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

" Filesystem git lookup; no process spawn. Cached per starting directory.
" Also used by git signs. Walks parents until .git is a dir or a gitfile
" (worktrees / submodules). Empty string means "not in a repository".
let s:git_root_cache = {}
let s:git_dir_cache = {}

function! s:GitRoot(path) abort
    if empty(a:path)
        return ''
    endif
    let l:dir = fnamemodify(a:path, ':p:h')
    if has_key(s:git_root_cache, l:dir)
        return s:git_root_cache[l:dir]
    endif

    let l:cur = l:dir
    let l:root = ''
    while 1
        if isdirectory(l:cur . '/.git') || filereadable(l:cur . '/.git')
            let l:root = l:cur
            break
        endif
        let l:parent = fnamemodify(l:cur, ':h')
        if l:parent ==# l:cur
            break
        endif
        let l:cur = l:parent
    endwhile
    let s:git_root_cache[l:dir] = l:root
    return l:root
endfunction

" Resolve $GIT_DIR. Regular repos use <root>/.git/; worktrees store
" "gitdir: <path>" in that file.
function! s:GitDir(root) abort
    if empty(a:root)
        return ''
    endif
    if has_key(s:git_dir_cache, a:root)
        return s:git_dir_cache[a:root]
    endif

    let l:git = a:root . '/.git'
    let l:dir = ''
    if isdirectory(l:git)
        let l:dir = l:git
    elseif filereadable(l:git)
        let l:line = get(readfile(l:git, '', 1), 0, '')
        let l:gitdir = matchstr(l:line, '^gitdir:\s*\zs.*')
        if !empty(l:gitdir)
            if l:gitdir !~# '^[/\\]\|^\a:'
                let l:gitdir = a:root . '/' . l:gitdir
            endif
            let l:dir = substitute(fnamemodify(l:gitdir, ':p'), '[/\\]$', '', '')
        endif
    endif
    let s:git_dir_cache[a:root] = l:dir
    return l:dir
endfunction

" Cheap invalidation key: HEAD or index mtime changed => refresh branch/signs.
function! s:GitStateStamp(root) abort
    let l:gitdir = s:GitDir(a:root)
    if empty(l:gitdir)
        return ''
    endif
    return getftime(l:gitdir . '/HEAD') . '/' . getftime(l:gitdir . '/index')
endfunction

" Path relative to the repo root, as git ls-files / git diff expect.
function! s:GitRelativePath(root, path) abort
    let l:root = substitute(fnamemodify(a:root, ':p'), '[/\\]$', '', '')
    let l:path = fnamemodify(a:path, ':p')
    if strpart(l:path, 0, strlen(l:root)) !=# l:root
        return ''
    endif
    return substitute(strpart(l:path, strlen(l:root)), '^[/\\]', '', '')
endfunction

" Reload-safe: kill in-flight git symbolic-ref jobs from a previous :source.
if exists('s:git_branch_jobs')
    for s:git_branch_job in values(s:git_branch_jobs)
        try
            call job_stop(s:git_branch_job, 'kill')
        catch
        endtry
    endfor
endif
let s:git_branch_jobs = {}
let s:git_branch_by_root = {}
let s:git_branch_stamp = {}

function! s:GitBranchOut(root, channel, msg) abort
    let s:git_branch_by_root[a:root] = trim(a:msg)
    redrawstatus
endfunction

function! s:GitBranchExit(root, job, status) abort
    if has_key(s:git_branch_jobs, a:root)
        call remove(s:git_branch_jobs, a:root)
    endif
    if !has_key(s:git_branch_by_root, a:root)
        let s:git_branch_by_root[a:root] = ''
    endif
    let s:git_branch_stamp[a:root] = s:GitStateStamp(a:root)
    redrawstatus
endfunction

" One job per repo root. Detached HEAD falls back to the short commit hash.
function! s:RefreshGitBranchAsync(root) abort
    if !has('job') || !executable('git') || empty(a:root)
        return
    endif
    if has_key(s:git_branch_jobs, a:root)
        return
    endif

    let l:cmd = 'git -C ' . shellescape(a:root)
        \ . ' symbolic-ref --quiet --short HEAD 2>/dev/null'
        \ . ' || git -C ' . shellescape(a:root)
        \ . ' rev-parse --short HEAD 2>/dev/null'
    let s:git_branch_jobs[a:root] = job_start(['sh', '-c', l:cmd], {
        \ 'in_io': 'null',
        \ 'err_io': 'null',
        \ 'out_mode': 'nl',
        \ 'out_cb': function('<SID>GitBranchOut', [a:root]),
        \ 'exit_cb': function('<SID>GitBranchExit', [a:root])
        \ })
endfunction

" Statusline callback: return cached branch text, and start a refresh if
" HEAD/index changed. Must stay cheap; it runs on every statusline redraw.
function! BeauGitBranch() abort
    if &buftype !=# '' || empty(expand('%:p'))
        return ''
    endif

    let l:root = s:GitRoot(expand('%:p'))
    if empty(l:root)
        return ''
    endif

    let l:stamp = s:GitStateStamp(l:root)
    if get(s:git_branch_stamp, l:root, '') !=# l:stamp
            \ || !has_key(s:git_branch_by_root, l:root)
        call s:RefreshGitBranchAsync(l:root)
    endif

    let l:branch = get(s:git_branch_by_root, l:root, '')
    return empty(l:branch) ? '' : ' 🅑  ' . l:branch
endfunction

function! s:ApplyStatuslineColors() abort
    highlight BeauStatusMode cterm=bold ctermfg=0 ctermbg=12
        \ gui=bold guifg=#1a1b26 guibg=#7aa2f7
    highlight BeauStatusFile cterm=NONE ctermfg=15 ctermbg=8
        \ gui=NONE guifg=#c0caf5 guibg=#32344a
    highlight BeauStatusGit cterm=bold ctermfg=10 ctermbg=8
        \ gui=bold guifg=#9ece6a guibg=#32344a
    highlight BeauStatusMeta cterm=bold ctermfg=0 ctermbg=12
        \ gui=bold guifg=#1a1b26 guibg=#7aa2f7
endfunction

call s:ApplyStatuslineColors()

augroup beau_statusline_colors
    autocmd!
    autocmd ColorScheme * call <SID>ApplyStatuslineColors()
augroup END

augroup beau_git_branch_status
    autocmd!
    autocmd DirChanged,FocusGained * redrawstatus
augroup END

" %S is the pending showcmd (operators/counts) because showcmdloc=statusline.
set statusline=
let &statusline .= '%#BeauStatusMode# BEAU:%{BeauStatusMode()} '
set statusline+=%#BeauStatusFile#\ %<%F
let &statusline .= '%#BeauStatusGit#%{BeauGitBranch()}'
set statusline+=\ %h%m%r%w\ %S
set statusline+=%=
let &statusline .= '🅡  %#BeauStatusMeta# %y %l:%c %p%% '

" --- Command-line UI ---------------------------------------------------------
" Style the native ':' command line as a thin bottom command panel.
" Temporarily link MsgArea to Pmenu and hide showcmd so the panel is uncluttered.
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

" --- Floating terminal -------------------------------------------------------
" Reusable floating shell. buf holds the job; win is the popup.
" Hide (Space-t / Ctrl-Q) keeps the process and cwd; Esc Esc wipes it.
" exists() keeps the job alive across :source $MYVIMRC.
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

" popup_create leaves Terminal-Normal; feed 'i' so the shell accepts keys.
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
    " Keep mouse-wheel scrolling without showing a popup scrollbar.
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <ScrollWheelUp> '
        \ . '<C-\><C-N>3k')
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <ScrollWheelDown> '
        \ . '<C-\><C-N>3j')
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <S-ScrollWheelUp> '
        \ . '<C-\><C-N>15k')
    call win_execute(s:floating_terminal.win,
        \ 'tnoremap <silent> <buffer> <S-ScrollWheelDown> '
        \ . '<C-\><C-N>15j')
    " Keep handling the wheel while the terminal is in Terminal-Normal mode.
    call win_execute(s:floating_terminal.win,
        \ 'nnoremap <silent> <buffer> <ScrollWheelUp> 3k')
    call win_execute(s:floating_terminal.win,
        \ 'nnoremap <silent> <buffer> <ScrollWheelDown> 3j')
    call win_execute(s:floating_terminal.win,
        \ 'nnoremap <silent> <buffer> <S-ScrollWheelUp> 15k')
    call win_execute(s:floating_terminal.win,
        \ 'nnoremap <silent> <buffer> <S-ScrollWheelDown> 15j')
endfunction

" Visible => hide popup. Dead job => start a new shell. Else reuse buf.
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
            \ 'term_name': ' 🅣  HUSTLE ',
            \ 'term_highlight': 'BeauTerminal',
            \ 'term_rows': l:size.minheight,
            \ 'term_cols': l:size.minwidth
            \ })
        if s:floating_terminal.buf <= 0
            echoerr 'Unable to start floating terminal'
            return
        endif
        call setbufvar(s:floating_terminal.buf, '&bufhidden', 'hide')
        " Keep enough terminal history for mouse-wheel review.
        call setbufvar(s:floating_terminal.buf, '&termwinscroll', 2000)
        call term_setkill(s:floating_terminal.buf, 'kill')
    endif

    let l:options = extend(l:size, {
        \ 'pos': 'center',
        \ 'border': [1, 1, 1, 1],
        \ 'borderchars': ['─', '│', '─', '│', '┌', '┐', '┘', '└'],
        \ 'padding': [0, 1, 0, 1],
        \ 'title': ' 🅣  HUSTLE ',
        \ 'close': 'none',
        \ 'drag': 1,
        \ 'resize': 1,
        \ 'scrollbar': 0,
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

" --- fzf / live ripgrep ------------------------------------------------------
" ~/.fzf is the fzf binary install; fzf.vim is a pack plugin under ~/.vim.
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
" Space-fl / :BLines: exact substrings only, not fuzzy character matching.
let g:fzf_vim.blines_options = ['--exact']

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

" All Files/Rg variants stay anchored to the directory where Vim started,
" even after :cd or NERDTree. exists() preserves the root across :source.
if !exists('g:beau_workspace_root')
    let g:beau_workspace_root = getcwd()
endif

function! s:FzfVimAvailable() abort
    return get(g:, 'loaded_fzf_vim', 0) || exists(':Files') == 2
endfunction

" a:regex 0 => --fixed-strings (Space-fg). 1 => ripgrep regex (Space-re).
function! s:LiveRg(query, fullscreen, regex) abort
    if !executable('rg')
        echoerr 'Rg requires ripgrep (rg) in PATH'
        return
    endif
    if !s:FzfVimAvailable()
        echoerr 'fzf.vim is not available'
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

" --- Git signs ---------------------------------------------------------------
" Signcolumn +/-/~ for the current buffer vs HEAD. Replaces the old popup.
" Reload-safe: stop leftover minimap popup/timer and in-flight git diff jobs.
" s:git_signs.gen drops stale job output; .cache skips unchanged files;
" .dirty queues a second refresh if the buffer changed while a job ran.
if exists('s:git_minimap_timer')
    call timer_stop(s:git_minimap_timer)
    unlet s:git_minimap_timer
endif
if exists('s:git_minimap')
    try
        if get(s:git_minimap, 'win', -1) > 0
            call popup_close(s:git_minimap.win)
        endif
    catch
    endtry
    let s:git_minimap_buf = get(s:git_minimap, 'buf', -1)
    unlet s:git_minimap
    if s:git_minimap_buf > 0 && bufexists(s:git_minimap_buf)
        execute 'silent! bwipeout!' s:git_minimap_buf
    endif
    unlet s:git_minimap_buf
endif

if exists('s:git_signs') && has_key(s:git_signs, 'jobs')
    for s:git_sign_job in values(s:git_signs.jobs)
        try
            call job_stop(s:git_sign_job, 'kill')
        catch
        endtry
    endfor
endif
if exists('s:git_signs') && get(s:git_signs, 'timer', -1) > 0
    call timer_stop(s:git_signs.timer)
endif
let s:git_signs = {
    \ 'enabled': 1,
    \ 'jobs': {},
    \ 'gen': {},
    \ 'out': {},
    \ 'cache': {},
    \ 'dirty': {},
    \ 'timer': -1,
    \ 'pending_buf': 0
    \ }

function! s:GitSignsSupported() abort
    return has('signs') && has('job') && executable('git')
endfunction

function! s:ApplyGitSignColors() abort
    highlight BeauGitSignAdd cterm=bold ctermfg=10 ctermbg=NONE
        \ gui=bold guifg=#9ece6a guibg=NONE
    highlight BeauGitSignChange cterm=bold ctermfg=11 ctermbg=NONE
        \ gui=bold guifg=#e0af68 guibg=NONE
    highlight BeauGitSignDelete cterm=bold ctermfg=9 ctermbg=NONE
        \ gui=bold guifg=#f7768e guibg=NONE
    if !s:GitSignsSupported()
        return
    endif
    call sign_define('BeauGitAdd', {
        \ 'text': '+ ',
        \ 'texthl': 'BeauGitSignAdd'
        \ })
    call sign_define('BeauGitChange', {
        \ 'text': '~ ',
        \ 'texthl': 'BeauGitSignChange'
        \ })
    call sign_define('BeauGitDelete', {
        \ 'text': '- ',
        \ 'texthl': 'BeauGitSignDelete'
        \ })
endfunction

function! s:GitSignsUnplace(buf) abort
    if !has('signs') || a:buf <= 0 || !bufexists(a:buf)
        return
    endif
    try
        call sign_unplace('beau_git', {'buffer': a:buf})
    catch
    endtry
endfunction

" Parse unified-diff hunks (git diff -U0). Cap at 2000 marks so a huge
" rewrite does not flood the signcolumn.
function! s:GitSignsParseHunks(lines, line_count) abort
    let l:count = max([1, a:line_count])
    let l:marks = {}
    for l:diff_line in a:lines
        let l:hunk = matchlist(l:diff_line,
            \ '^@@ -\(\d\+\)\%([,]\(\d\+\)\)\?'
            \ . ' +\(\d\+\)\%([,]\(\d\+\)\)\? @@')
        if empty(l:hunk)
            continue
        endif
        let l:old_count = empty(l:hunk[2]) ? 1 : str2nr(l:hunk[2])
        let l:new_start = str2nr(l:hunk[3])
        let l:new_count = empty(l:hunk[4]) ? 1 : str2nr(l:hunk[4])
        if l:new_count == 0
            let l:index = max([1, min([l:count, l:new_start])])
            let l:marks[l:index] = 'BeauGitDelete'
        else
            let l:name = l:old_count > 0 ? 'BeauGitChange' : 'BeauGitAdd'
            let l:last = min([l:count, l:new_start + l:new_count - 1])
            if l:new_start <= l:last
                for l:index in range(l:new_start, l:last)
                    let l:marks[l:index] = l:name
                endfor
            endif
        endif
        if len(l:marks) > 2000
            return {}
        endif
    endfor
    return l:marks
endfunction

function! s:GitSignsPlace(buf, marks) abort
    call s:GitSignsUnplace(a:buf)
    if empty(a:marks) || !bufexists(a:buf)
        return
    endif
    let l:list = []
    for l:lnum in keys(a:marks)
        call add(l:list, {
            \ 'buffer': a:buf,
            \ 'group': 'beau_git',
            \ 'id': str2nr(l:lnum),
            \ 'lnum': str2nr(l:lnum),
            \ 'name': a:marks[l:lnum]
            \ })
    endfor
    try
        call sign_placelist(l:list)
    catch
    endtry
endfunction

function! s:GitSignsOut(buf, gen, channel, msg) abort
    if get(s:git_signs.gen, a:buf, 0) != a:gen
        return
    endif
    if !has_key(s:git_signs.out, a:buf)
        let s:git_signs.out[a:buf] = []
    endif
    call add(s:git_signs.out[a:buf], a:msg)
endfunction

function! s:GitSignsExit(buf, gen, line_count, cache_key, job, status) abort
    if has_key(s:git_signs.jobs, a:buf)
        call remove(s:git_signs.jobs, a:buf)
    endif
    if get(s:git_signs.gen, a:buf, 0) != a:gen || !bufexists(a:buf)
        return
    endif

    let l:lines = get(s:git_signs.out, a:buf, [])
    if has_key(s:git_signs.out, a:buf)
        call remove(s:git_signs.out, a:buf)
    endif

    if empty(l:lines) || l:lines[0] ==# 'UNTRACKED'
        call s:GitSignsUnplace(a:buf)
        let s:git_signs.cache[a:buf] = a:cache_key
    else
        let l:diff = l:lines[0] ==# 'TRACKED' ? l:lines[1:] : l:lines
        let l:marks = s:GitSignsParseHunks(l:diff, a:line_count)
        call s:GitSignsPlace(a:buf, l:marks)
        let s:git_signs.cache[a:buf] = a:cache_key
    endif

    if get(s:git_signs.dirty, a:buf, 0)
        call remove(s:git_signs.dirty, a:buf)
        let s:git_signs.pending_buf = a:buf
        call s:GitSignsRefresh()
    endif
endfunction

function! s:GitSignsOnDelete(buf) abort
    let l:buf = str2nr(a:buf)
    if has_key(s:git_signs.jobs, l:buf)
        try
            call job_stop(s:git_signs.jobs[l:buf], 'kill')
        catch
        endtry
        call remove(s:git_signs.jobs, l:buf)
    endif
    for l:key in ['gen', 'out', 'cache', 'dirty']
        if has_key(s:git_signs[l:key], l:buf)
            call remove(s:git_signs[l:key], l:buf)
        endif
    endfor
endfunction

" Skip special buffers, unreadable paths, files outside a repo, and
" buffers larger than 20000 lines. Cache key is path + mtime + linecount + HEAD.
function! s:GitSignsRefresh(...) abort
    if !s:git_signs.enabled || !s:GitSignsSupported()
        return
    endif

    let l:buf = get(s:git_signs, 'pending_buf', 0)
    if l:buf <= 0 || !bufexists(l:buf)
        let l:buf = bufnr('%')
    endif
    if l:buf <= 0 || !bufexists(l:buf)
        return
    endif

    if getbufvar(l:buf, '&buftype') !=# ''
        return
    endif
    let l:path = fnamemodify(bufname(l:buf), ':p')
    if empty(l:path) || !filereadable(l:path)
        call s:GitSignsUnplace(l:buf)
        return
    endif

    let l:root = s:GitRoot(l:path)
    if empty(l:root)
        call s:GitSignsUnplace(l:buf)
        if has_key(s:git_signs.cache, l:buf)
            call remove(s:git_signs.cache, l:buf)
        endif
        return
    endif
    let l:relative = s:GitRelativePath(l:root, l:path)
    if empty(l:relative)
        call s:GitSignsUnplace(l:buf)
        return
    endif

    let l:info = getbufinfo(l:buf)
    let l:line_count = empty(l:info) ? 0 : l:info[0].linecount
    let l:key = l:path . "\n" . string(getftime(l:path))
        \ . "\n" . string(l:line_count)
        \ . "\n" . s:GitStateStamp(l:root)
    if l:line_count > 20000
        call s:GitSignsUnplace(l:buf)
        let s:git_signs.cache[l:buf] = l:key
        return
    endif
    if get(s:git_signs.cache, l:buf, '') ==# l:key
        return
    endif
    if has_key(s:git_signs.jobs, l:buf)
        let s:git_signs.dirty[l:buf] = 1
        return
    endif

    let l:gen = get(s:git_signs.gen, l:buf, 0) + 1
    let s:git_signs.gen[l:buf] = l:gen
    let s:git_signs.out[l:buf] = []
    " argv: $1=repo root, $2=relative path. TRACKED/UNTRACKED is the first line.
    let l:job = job_start([
        \ 'sh', '-c',
        \ 'if git -C "$1" ls-files --error-unmatch -- "$2" >/dev/null 2>&1; then'
        \ . ' printf "%s\n" TRACKED;'
        \ . ' git -C "$1" diff --no-color --unified=0 HEAD -- "$2";'
        \ . ' else printf "%s\n" UNTRACKED; fi',
        \ '_', l:root, l:relative
        \ ], {
        \ 'in_io': 'null',
        \ 'err_io': 'null',
        \ 'out_mode': 'nl',
        \ 'out_cb': function('<SID>GitSignsOut', [l:buf, l:gen]),
        \ 'exit_cb': function('<SID>GitSignsExit',
        \     [l:buf, l:gen, l:line_count, l:key])
        \ })
    if job_status(l:job) ==# 'fail'
        return
    endif
    let s:git_signs.jobs[l:buf] = l:job
endfunction

function! s:GitSignsRefreshSoon(...) abort
    let s:git_signs.pending_buf = bufnr('%')
    if s:git_signs.timer > 0
        call timer_stop(s:git_signs.timer)
    endif
    let s:git_signs.timer = timer_start(80, function('<SID>GitSignsRefresh'))
endfunction

function! s:GitSignsDisable() abort
    let s:git_signs.enabled = 0
    if s:git_signs.timer > 0
        call timer_stop(s:git_signs.timer)
        let s:git_signs.timer = -1
    endif
    if has('signs')
        try
            call sign_unplace('beau_git')
        catch
        endtry
    endif
    let s:git_signs.cache = {}
endfunction

function! s:GitSignsEnable() abort
    let s:git_signs.enabled = 1
    let s:git_signs.pending_buf = bufnr('%')
    call s:GitSignsRefresh()
endfunction

call s:ApplyGitSignColors()
augroup beau_git_signs
    autocmd!
    autocmd ColorScheme * call <SID>ApplyGitSignColors()
    autocmd VimEnter,BufEnter,BufReadPost,BufWritePost,FocusGained *
        \ call <SID>GitSignsRefreshSoon()
    autocmd BufDelete,BufWipeout * call <SID>GitSignsOnDelete(expand('<abuf>'))
augroup END

" --- Plugin knobs ------------------------------------------------------------
" NERDTree file explorer; never change Vim's working directory (ChDirMode=0).
let g:NERDTreeWinSize = 35
let g:NERDTreeWinSizeMax = 40
let g:NERDTreeShowHidden = 1
let g:NERDTreeAutoCenter = 1
let g:NERDTreeChDirMode = 0
let g:NERDTreeRespectWildIgnore = 1
let g:NERDTreeMinimalUI = 1
" netrw fallback file explorer
let g:netrw_winsize   = 20
let g:netrw_liststyle = 3
let g:netrw_hide      = 1
let g:netrw_banner    = 0
let g:netrw_keepdir   = 1
let g:netrw_sort_by   = "name"

" Tagbar outline uses source order, which is more useful for C/C++.
let g:tagbar_compact = 1
let g:tagbar_autofocus = 1
let g:tagbar_sort = 0
let g:tagbar_width = 32
let g:tagbar_silent = 1

" NERDCommenter: keep default maps and add Space-/ as a toggle.
let g:NERDSpaceDelims = 1
let g:NERDDefaultAlign = 'left'
let g:NERDCommentEmptyLines = 1
let g:NERDTrimTrailingWhitespace = 1
let g:NERDCreateDefaultMappings = 1

" Copy the selected NERDTree node path. yr = relative, ya = absolute.
" Always fills register p so Space-ip works without a clipboard provider.
function! s:NERDTreeCopyPath(absolute) abort
    try
        let l:node = g:NERDTreeFileNode.GetSelected()
        let l:path = l:node.path.str()
    catch
        echohl WarningMsg
        echomsg 'NERDTree: no file or directory is selected'
        echohl None
        return
    endtry

    let l:path = a:absolute ? fnamemodify(l:path, ':p') : fnamemodify(l:path, ':.')
    " Keep a private register as a clipboard-independent fallback.
    call setreg('p', l:path, 'v')
    if has('clipboard')
        call setreg('+', l:path, 'v')
    endif
    echomsg 'Path copied: ' . l:path
endfunction

function! s:PasteNERDTreePath() abort
    if empty(getreg('p'))
        echohl WarningMsg
        echomsg 'No NERDTree path has been copied yet'
        echohl None
        return
    endif
    normal! "pp
endfunction

function! s:DefineNERDTreePathMappings() abort
    nnoremap <silent><buffer> yr :call <SID>NERDTreeCopyPath(0)<CR>
    nnoremap <silent><buffer> ya :call <SID>NERDTreeCopyPath(1)<CR>
endfunction

augroup beau_nerdtree_paths
    autocmd!
    autocmd FileType nerdtree call <SID>DefineNERDTreePathMappings()
augroup END

" --- Commands and leader maps ------------------------------------------------
function! s:LeaderFHint() abort
    echo 'fe files  fg grep  fw word  fl lines  fb buffers  fh recent  fc commands'
endfunction

function! s:WorkspaceFiles() abort
    if !s:FzfVimAvailable()
        echoerr 'fzf.vim is not available'
        return
    endif
    execute 'Files' fnameescape(g:beau_workspace_root)
endfunction

function! s:BufferLines() abort
    " Each token is an exact substring.  'sos kick nebula' keeps lines that
    " contain all three strings, and drops fuzzy hits such as 'sxxxx oxs'.
    if !s:FzfVimAvailable()
        echoerr 'fzf.vim is not available'
        return
    endif
    call fzf#vim#buffer_lines({
        \ 'options': ['--exact', '--prompt', 'Lines> ']
        \ })
endfunction

function! s:FormatBuffer() abort
    if empty(&formatprg)
        echo 'No formatprg for this filetype'
        return
    endif
    let l:view = winsaveview()
    silent execute 'keepjumps normal! gggqG'
    call winrestview(l:view)
    echo 'Formatted with ' . &formatprg
endfunction

" Same directory first, then walk parents with findfile(). Not a project-wide
" ctags lookup; use Space-g / Space-s for that.
function! s:SwitchHeaderSource() abort
    let l:name = expand('%:t')
    if empty(l:name)
        echo 'No file name'
        return
    endif

    let l:stem = expand('%:t:r')
    let l:ext = expand('%:e')
    if l:ext =~? '^\(c\|cc\|cpp\|cxx\|c++\|C\)$'
        let l:alts = [l:stem . '.h', l:stem . '.hpp', l:stem . '.hh', l:stem . '.hxx']
    elseif l:ext =~? '^\(h\|hpp\|hh\|hxx\|H\)$'
        let l:alts = [l:stem . '.c', l:stem . '.cc', l:stem . '.cpp', l:stem . '.cxx']
    else
        echo 'Not a C/C++ header or source file'
        return
    endif

    let l:dir = expand('%:p:h')
    for l:alt in l:alts
        let l:same = l:dir . '/' . l:alt
        if filereadable(l:same)
            execute 'edit' fnameescape(l:same)
            return
        endif
    endfor
    for l:alt in l:alts
        let l:found = findfile(l:alt, l:dir . ';')
        if !empty(l:found)
            execute 'edit' fnameescape(fnamemodify(l:found, ':p'))
            return
        endif
    endfor
    echo 'No matching header/source for ' . l:name
endfunction

" Prefer GNU GLOBAL when GTAGS exists in a parent of the current file.
function! s:JumpGtagsCursor() abort
    if !empty(findfile('GTAGS', '.;')) && exists(':GtagsCursor')
        GtagsCursor
        return
    endif
    call s:FzfTagUnderCursor()
endfunction

function! s:GtagsRefs() abort
    let l:word = expand('<cword>')
    if empty(l:word)
        echo 'No symbol under cursor'
        return
    endif
    if !exists(':Gtags')
        echo 'gtags plugin is not available'
        return
    endif
    execute 'Gtags -r' l:word
endfunction

function! s:ToggleQuickfix() abort
    for l:win in getwininfo()
        if l:win.quickfix && !l:win.loclist
            cclose
            return
        endif
    endfor
    botright copen 10
endfunction

function! s:FzfTagUnderCursor() abort
    let l:symbol = expand('<cword>')
    if empty(l:symbol)
        echo 'No symbol under cursor'
        return
    endif
    if !s:FzfVimAvailable()
        echoerr 'fzf.vim is not available'
        return
    endif
    call fzf#vim#tags(l:symbol, fzf#vim#with_preview({
        \ 'placeholder': '--tag {2}:{-1}:{3..}'
        \ }), 0)
endfunction

command! Format call <SID>FormatBuffer()
command! -nargs=0 Debug packadd termdebug | Termdebug

" Leader map index (Space = <Leader>)
"   e  NERDTree toggle          f  find hint
"   fe workspace files          fg live rg (text)     fw word
"   fl buffer lines (exact)     fb buffers            fh recent files
"   fc commands                 re live rg (regex)
"   t  floating terminal        w  next window
"   g  fzf tags                 s  GtagsCursor / tags a  Gtags -r
"   o  Tagbar                   h  header <-> source  =  formatprg
"   q  quickfix                 /  comment toggle     b  jump back
"   d  next paragraph           u  prev paragraph
"   n  presentation view        m  restore editing view
"   ip paste NERDTree path (register p)
" NERDTree buffer: yr copy relative path, ya copy absolute path.
nnoremap <silent> <C-l> :nohlsearch<Bar>diffupdate<CR><C-l>
nnoremap n nzzzv
nnoremap N Nzzzv
nnoremap <silent> <Leader>ip :call <SID>PasteNERDTreePath()<CR>
nnoremap <silent> <Leader>e :NERDTreeToggle<CR>
nnoremap <silent> <Leader>f :call <SID>LeaderFHint()<CR>
xnoremap <silent> <Leader>f :<C-u>call <SID>LeaderFHint()<CR>
nnoremap <silent> <Leader>fe :call <SID>WorkspaceFiles()<CR>
nnoremap <silent> <Leader>fg :Rg<CR>
nnoremap <silent> <Leader>fw :call <SID>LiveRgWord()<CR>
xnoremap <silent> <Leader>fg :<C-u>call <SID>LiveRgVisual()<CR>
nnoremap <silent> <Leader>fl :call <SID>BufferLines()<CR>
nnoremap <silent> <Leader>fb :Buffers<CR>
nnoremap <silent> <Leader>fh :History<CR>
nnoremap <silent> <Leader>fc :Commands<CR>
nnoremap <silent> <Leader>re :RgRegex<CR>
nnoremap <silent> <Leader>t <Cmd>FloatTerminal<CR>
nnoremap <silent> <Leader>w <C-w><C-w>
nnoremap <silent> <Leader>g <Cmd>call <SID>FzfTagUnderCursor()<CR>
nnoremap <silent> <Leader>s :call <SID>JumpGtagsCursor()<CR>
nnoremap <silent> <Leader>a :call <SID>GtagsRefs()<CR>
nnoremap <silent> <Leader>o :TagbarToggle<CR>
nnoremap <silent> <Leader>h :call <SID>SwitchHeaderSource()<CR>
nnoremap <silent> <Leader>= :Format<CR>
nnoremap <silent> <Leader>q :call <SID>ToggleQuickfix()<CR>
nmap <silent> <Leader>/ <Plug>NERDCommenterToggle
xmap <silent> <Leader>/ <Plug>NERDCommenterToggle
nnoremap <silent> <Leader>b <C-o>
nnoremap <silent> <Leader>d }
nnoremap <silent> <Leader>u {
nnoremap <silent> <Leader>n
    \ :set nonumber norelativenumber nolist mouse=<CR>
    \ :call <SID>GitSignsDisable()<CR>
nnoremap <silent> <Leader>m
    \ :set number relativenumber list mouse=a<CR>
    \ :call <SID>GitSignsEnable()<CR>
" Insert completion uses Vim's built-in Ctrl-N and Ctrl-P.
