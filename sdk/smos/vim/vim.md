# Vim 开发环境

本文说明如何在 Linux 主机上安装 Vim，并将它用于 SMOS 的 Zircon、C/C++、Rust、汇编、GN 和 Markdown 文件。Vim 运行在主机上；它不会被打包进 SMOS，也不依赖目标 QEMU 镜像。

## 版本与目录约定

源码默认放在 `~/opt/vim-src`，安装前缀为 `~/opt`。使用固定 tag 可以让不同开发机上的编辑器行为更容易复现：

```sh
mkdir -p ~/opt
git clone https://github.com/vim/vim.git ~/opt/vim-src
cd ~/opt/vim-src

# 可选：将 <tag> 替换为团队约定的 Vim tag
git fetch --tags --depth=1
git checkout <tag>
```

检查主机工具链后再开始编译：

```sh
git --version
cc --version
make --version
python3 --version
```

## 安装依赖

下面的依赖覆盖当前配置中的终端版 Vim、Python 3、Perl、Lua、X11 和 cscope 支持。只需要终端编辑器时，可以去掉 X11 相关包和 `--with-x` 配置项。

```sh
sudo apt update
sudo apt install -y \
  build-essential \
  libncurses-dev \
  libx11-dev \
  libxt-dev \
  libsm-dev \
  libice-dev \
  libxpm-dev \
  python3-dev \
  libperl-dev \
  liblua5.4-dev \
  cscope \
  universal-ctags
```

`python3-config` 通常已经由 `python3-dev` 提供。确认 Python 配置目录可被 Vim 的 configure 脚本找到：

```sh
python3-config --configdir
```

## 编译和安装

在源码目录执行。`--prefix=$HOME/opt` 不会写入系统目录，因此不需要 `sudo make install`：

```sh
cd ~/opt/vim-src

./configure \
  --with-features=huge \
  --enable-multibyte \
  --enable-python3interp=yes \
  --with-python3-config-dir="$(python3-config --configdir)" \
  --enable-perlinterp=yes \
  --enable-luainterp=yes \
  --enable-cscope \
  --enable-gui=no \
  --with-x \
  --prefix="$HOME/opt"

make -j"$(nproc)"
make install
```

将安装目录加入当前 shell 的 `PATH`：

```sh
export PATH="$HOME/opt/bin:$PATH"
```

需要持久化时，将同一行加入 `~/.profile` 或所使用 shell 的启动文件，然后重新打开终端。确认实际调用的是新安装的 Vim：

```sh
command -v vim
vim --version | sed -n '1,8p'
vim --clean --not-a-term -Nu NONE -n +'quit'
```

最后一条命令用于检查 Vim 可以在无配置、无终端交互的情况下启动；如果只看到版本信息且退出码为 0，说明基础安装正常。

## 安装 SMOS 配置

从 SMOS 仓库根目录执行。安装前先备份现有配置；`.vimrc` 会创建 `~/.vim/swap` 和 `~/.vim/undo`，不会把恢复文件写入源码树：

```sh
cd /home/beau/clot/smos
[ -f "$HOME/.vimrc" ] && cp "$HOME/.vimrc" "$HOME/.vimrc.bak.$(date +%Y%m%d%H%M%S)"
install -Dm644 sdk/smos/vim/.vimrc "$HOME/.vimrc"
```

配置中的几个常用命令：

| 命令 | 用途 |
| --- | --- |
| `:BEAUStyle` | SMOS/Hypervisor 风格：8 列 tab |
| `:GOOGLEStyle` | Google C++ 风格：2 个空格 |
| `:LINUXStyle` | Linux 内核风格：8 列 tab |
| `:NERDTreeToggle` | 打开或关闭文件树 |
| `:Files` | 通过 fzf 查找文件 |
| `:Rg <pattern>` | 通过 fzf/rg 搜索源码 |
| `:Tags <symbol>` | 查找 ctags 符号 |

C/C++ 风格命令只影响当前 buffer。打开文件后执行 `gg=G` 可以按当前风格重新缩进已有内容。

## 安装插件

Vim 原生 package 目录会在启动时自动加载 `~/.vim/pack/*/start/*` 下的插件。先创建目录，再安装与 `.vimrc` 对应的插件：

```sh
mkdir -p ~/.vim/pack/plugins/start ~/.vim/pack/themes/start

git clone https://github.com/preservim/nerdtree.git \
  ~/.vim/pack/plugins/start/nerdtree
git clone https://github.com/jiangmiao/auto-pairs.git \
  ~/.vim/pack/plugins/start/auto-pairs
git clone https://github.com/preservim/nerdcommenter.git \
  ~/.vim/pack/plugins/start/nerdcommenter
git clone https://github.com/tpope/vim-surround.git \
  ~/.vim/pack/plugins/start/vim-surround
git clone https://github.com/vim-airline/vim-airline.git \
  ~/.vim/pack/plugins/start/vim-airline
git clone https://github.com/folke/tokyonight.vim.git \
  ~/.vim/pack/themes/start/tokyonight
git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
~/.fzf/install --all
git clone https://github.com/junegunn/fzf.vim.git \
  ~/.vim/pack/plugins/start/fzf
```

重复执行 `git clone` 会因目录已存在而失败；升级已有插件时使用 `git -C <plugin-dir> pull --ff-only`。离线环境可以将这些目录从已准备好的主机复制到相同的 package 路径。启动 Vim 后检查插件和配色是否生效：

```vim
:scriptnames
:echo has('python3')
:echo exists('*fzf#vim#files')
:colorscheme tokyonight
```

如果 `colorscheme tokyonight` 报错，先确认 `~/.vim/pack/themes/start/tokyonight/colors/tokyonight.vim` 存在，或暂时注释 `.vimrc` 中的 `colorscheme tokyonight` 以便诊断其他配置。

Vim 配置或插件发生变化后，至少执行一次无配置启动检查、一次目标架构编译和一次相应验证。本文只描述主机编辑器环境，不承诺插件在无网络或不同 Vim 版本上的完全兼容性。

---

Hustle Embedded OS.
