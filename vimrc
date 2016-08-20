" Basic settings.
set nocompatible	" Sane mode.
set encoding=utf8	" File encoding.
set history=100		" Command history.

" Disable crap.
set noerrorbells
set novisualbell

" Disable backup and swapfiles.
set nobackup
set nowb
set noswapfile

" Map ',' as leaderkey.
let mapleader = ","
let g:mapleader = ","

" Automatically re-read the file, if it has been changed externally.
set autoread

" Appearance
syntax enable		" Syntax highlighting.
set scrolloff=6		" Min lines below/above cursor.
set number		" Enable line numbering.
set ruler		" Enable line/column ruler.
set cmdheight=1		" Command bar height.

" Searching
set hlsearch
set incsearch

" Command completion
set wildmenu
set wildmode=longest:full,full

" Backspace handling: No backspace over eol. Use <S-j> instead.
set backspace=indent,start

" Move between windows
map <C-j> <C-W>j
map <C-k> <C-W>k
map <C-h> <C-W>h
map <C-l> <C-W>l

" Move line up/down (normal mode only)
nmap <M-j> mz:m+<cr>`z
nmap <M-k> mz:m-2<cr>`z

" Toggle spell checking
map <leader>s :setlocal spell!<cr>

" Toggle paste mode
map <leader>p :setlocal paste!<cr>

" Indent
set autoindent
set smartindent
set tabstop=8
set shiftwidth=8
set softtabstop=0
set noexpandtab
set smarttab
map <leader><F2> :set ts=2 sw=2 expandtab<cr>
map <leader>2 :set ts=2 sw=2 noexpandtab<cr>
map <leader><F4> :set ts=4 sw=4 expandtab<cr>
map <leader>4 :set ts=4 sw=4 noexpandtab<cr>
map <leader><F8> :set ts=8 sw=8 expandtab<cr>
map <leader>8 :set ts=8 sw=8 noexpandtab<cr>
map <leader>r :retab<cr>