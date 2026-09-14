# Oh My Theme

Theme manager for [Oh My Posh](https://ohmyposh.dev/) that lets you browse, preview, install, activate, add custom and tweak themes directly inside your terminal.

![Screenshot-main](./img/ohmytheme-main.png)

![Screenshot-install](./img/ohmytheme-install.png)

## Features

- 💻 **Fast and simple**: runs from terminal. Simple interface.
- 🔍 **Real-time Search**: Filter local and remote theme repo
- ⚡ **Fast Installation**: Single or multiple theme download
- 🔄 **Easy Theme Switching**: Theme activation (Bash/Zsh/Fish) 
- 🗂️ **Dual Panel Interface**: Local and remote theme management
- 🎯 **Custom Repositories**: Add themes from Git repository (json has to be in root)
- 🎨 **Theme Customization**: Built-in color editor
- 🎨 **Basic Previews**: Sample prompt structure with basic metadata (Name, Version, Source, Color variation)
- 🚀 **Performance Optimized**: Smart caching and modular architecture

## Prerequisites

Before using this tool, you need:

1. **Oh My Posh installed** - Visit [ohmyposh.dev](https://ohmyposh.dev/) for installation instructions
2. **Compatible shell**: Bash, Zsh, or Fish
3. **Python 3.6+** with standard libraries

## Installation

### Method 1: PyPI (Recommended)
```bash
pip install oh-my-theme
```

### Method 2: AUR (Arch Linux)
```bash
yay -S oh-my-theme
# or
paru -S oh-my-theme
```

### Method 3: Git Clone
```bash
git clone https://github.com/mikeisfree/oh-my-theme.git
cd oh-my-theme
pip install -e .
# or, using uv:
uv pip install -e .
```

## Usage After Installation

Once installed run with:
```bash
omt
```

## Shell Config

The tool automatically updates your shell configuration:

- **Bash**: `~/.bashrc`
- **Zsh**: `~/.zshrc` 
- **Fish**: `~/.config/fish/config.fish`



### Clean Theme Management:
- **Removes** all existing Oh My Posh theme lines when activating a new theme - If You want to keep existing oh-my-posh configuration commenting it out will not be enough - back it up to a separate file! 
- **Adds** only the new active theme command
- **Preserves** all other shell configuration! (aliases, exports, functions)



After activating a theme, reload your shell:
```bash
source ~/.bashrc    # For Bash
source ~/.zshrc     # For Zsh
```

![Screenshot-local](./img/ohmytheme-localmenu.png)

## Usage Details

### Interface Overview

The tool displays two panels:
- **Left Panel**: installed themes (local)
- **Right Panel**: Available themes from Oh My Posh main repository + custom repos added by user (remote)

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `TAB` | Switch between panels |
| `↑/↓` | Navigate theme list |
| `ENTER` | Activate/Remove/Customize local theme or Select remote theme |
| `SPACE` | Toggle selection for remote themes |
| `p` | Preview selected theme |
| `i` | Install selected remote themes |
| `/` | **NEW**: Enter search mode for real-time theme filtering |
| `+` | **NEW**: Add custom Git repository |
| `ESC` | Exit search mode & cancel dialogs |
| `q` | Quit application |

### Local Theme Actions (ENTER)

When you press ENTER on a local theme, you'll see these options:
- `A` - **Activate** theme in shell
- `R` - **Remove** theme  
- `C` - **Customize** theme colors

### Getting Started

1. **Browse Remote Themes**: Use `TAB` to switch to the right panel and browse available themes
2. **Search Themes**: Press `/` to search and filter themes in real-time
3. **Preview Themes**: Press `p` to see previews with sample prompts and metadata
4. **Select Themes**: Use `SPACE` to select multiple themes for installation
5. **Install Themes**: Press `i` to download selected themes
6. **Activate Theme**: Switch to local panel (`TAB`) and press `ENTER` → `A` on your desired theme
7. **Customize Theme**: Press `ENTER` → `C` on local themes to edit colors
8. **Add Custom Repos**: Press `+` to add themes from custom Git repositories

### Theme Previews

Preview feature shows:
- **Sample prompt structure** git status, paths, segments
- **Essential metadata**: Name, Version, Source (git repository), Color variation

![Screenshot-preview](./img/ohmytheme-prev.png)

### Filter

- Press `/` to enter search mode
- Type to filter themes in real-time across both local and remote panels
- Search results highlight matching text
- Press `ESC` to exit search and process filtered items 

### Custom Repository Support

- Press `+` to add themes from custom Git repository
- Enter the Git repository URL when prompted
- The tool will fetch all `.omp.json` files from the repository root
- Custom themes are downloaded to your local themes directory
- repository address will be added to filter array 

![Screenshot-custom](./img/ohmytheme-custom.png)

### Theme Customization

- Select any local theme and press `ENTER` → `C`
- Visual color editor shows current segment colors
- Simple color picker interface for modifications
- Save as new theme (new json file) or overwrite original
- Preserve customizations across updates

![Screenshot-customizer](./img/ohmytheme-customizer.png)

## Theme Storage

Downloaded themes are stored in `~/.poshthemes/` directory. The tool manages this directory automatically.

## Troubleshooting

### "Unsupported shell" Error
Make sure your `SHELL` environment variable is set correctly:
```bash
echo $SHELL
```

## Safety measures:

### Backup-friendly: Uses a clean replacement strategy that preserves non-Oh My Posh configurations
### Atomic updates: Reads entire file, modifies in memory, then writes back
### Error handling: Returns success/failure status
### uses regex pattern to identify Oh My Posh lines:
```bash
init_pattern = re.compile(r"^\s*(eval.*oh-my-posh init.*|oh-my-posh init.*fish.*)")
```
### User confirmation: Always asks for confirmation before activating themes

### Theme Not Activating
1. Ensure Oh My Posh is properly installed and in your PATH
2. Check that your shell configuration file exists and is writable
3. Reload your shell after theme activation

### Preview Not Working
- For remote themes: The tool will offer to download the theme for preview
- For local themes: Ensure the theme file exists in `~/.poshthemes/`

### Search Not Responding
- Make sure you're in search mode (press `/` first)
- Press `ESC` to exit search mode if stuck
- Search works across both local and remote theme panels

### Custom Repository Issues
- Ensure the Git repository URL is valid and accessible
- Repository must contain `.omp.json` files in the root directory
- Check your internet connection for repository access

### Theme Customization Problems
- Only local themes can be customized
- Ensure you have write permissions to the themes directory
- Invalid JSON themes cannot be edited safely

## Performance Features

- **Smart Caching**: Theme metadata is cached to speed up repeated previews
- **File Reuse**: Existing downloaded themes are reused for previews
- **Memory Management**: Cache size is limited to prevent memory bloat
- **Lazy Loading**: Theme parsing only when needed

## What's New in v2.0

- 🔍 **Search**: Filter themes instantly with `/` keybind
- 🎯 **Custom Repositories**: Add themes from Git repository with `+` keybind  
- 🎨 **Theme Customization**: Built-in color editor for personalizing themes
- ✨ **Enhanced Previews**: sample prompts with essential metadata
- 🏗️ **Modular Architecture**: Improved code organization and maintainability

## Contributing

⭐ Star on GitHub if you like it!  
📦 Review the package on PyPI or AUR  
🐛 Report issues on GitHub  
🔧 Submit pull requests with updates/upgrades

## License

This project is open source. Please check the license file for details.

## Architecture

Oh My Theme v2.0 features a modular architecture:

- **`oh_my_theme/main.py`**: Core UI and application logic
- **`oh_my_theme/preview.py`**: Enhanced theme previews and sample generation
- **`oh_my_theme/search.py`**: Real-time search and filtering functionality
- **`oh_my_theme/repositories.py`**: Custom Git repository management
- **`oh_my_theme/editor.py`**: Theme color customization interface
- **`oh_my_theme/config.py`**: Configuration and settings management

## Dependencies

- **Python 3.6+**: Core runtime requirement
- **Standard libraries only** on Linux/macOS: curses, json, os, subprocess, urllib
- **Windows**: also installs `windows-curses` automatically (curses isn't built into Python on Windows)

## Related Links

- [Oh My Posh Official Website](https://ohmyposh.dev/)
- [Oh My Posh Documentation](https://ohmyposh.dev/docs/)
- [Oh My Posh Themes Repository (main)](https://github.com/JanDeDobbeleer/oh-my-posh/tree/main/themes)
- [Project Repository](https://github.com/mikeisfree/ohmytheme)
- [PyPI Package](https://pypi.org/project/oh-my-theme/)

---

**Note**: This tool modifies your shell configuration files. It's recommended to backup your configuration before first use.

