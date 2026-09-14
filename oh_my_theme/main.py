import os
import sys
import json
import re
import curses
from urllib import request
from collections import OrderedDict
import time

# Import new modules for search and repository functionality
try:
    from .search import handle_search_mode, filter_themes, draw_panel_with_search
    from .repositories import handle_add_repository
except ImportError:
    # Fallback for when running main.py directly
    from search import handle_search_mode, filter_themes, draw_panel_with_search
    from repositories import handle_add_repository

# --- Configuration ---
API_URL = "https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/contents/themes"
THEMES_DIR = os.path.expanduser("~/.poshthemes")

# --- Caching Configuration ---
MAX_CACHE_SIZE = 50  # Maximum number of cached theme metadata entries
CACHE_EXPIRY_SECONDS = 300  # 5 minutes cache expiry for file modification checks

# --- Data Fetching ---

def fetch_remote_themes():
    """Fetches the list of available themes from all repositories (official + custom)."""
    all_themes = set()
    
    # Fetch from official Oh My Posh repository
    try:
        with request.urlopen(API_URL) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                theme_files = [item['name'] for item in data if item['name'].endswith('.omp.json')]
                official_themes = [theme.replace('.omp.json', '') for theme in theme_files]
                all_themes.update(official_themes)
    except Exception:
        pass  # Continue even if official repo fails
    
    # Fetch from custom repositories
    try:
        from .config import get_custom_repositories
        from .repositories import fetch_themes_from_repo
    except ImportError:
        # Fallback for when running main.py directly
        from config import get_custom_repositories
        from repositories import fetch_themes_from_repo
    
    custom_repos = get_custom_repositories()
    for repo_url in custom_repos:
        try:
            theme_files, error_msg = fetch_themes_from_repo(repo_url)
            if not error_msg and theme_files:
                custom_themes = [theme_file['name'].replace('.omp.json', '') for theme_file in theme_files]
                all_themes.update(custom_themes)
        except Exception:
            continue  # Skip failed repositories
    
    return sorted(list(all_themes))

def get_local_themes():
    """Gets the list of themes already installed locally."""
    if not os.path.exists(THEMES_DIR):
        return []
    try:
        files = os.listdir(THEMES_DIR)
        themes = sorted([f.replace('.omp.json', '') for f in files if f.endswith('.omp.json')])
        return themes
    except OSError:
        return []

def get_active_theme(config_file):
    """Detects the currently active theme from shell config file."""
    if not os.path.exists(config_file):
        return None
    
    try:
        with open(config_file, "r") as f:
            lines = f.readlines()
        
        # Look for active oh-my-posh init line
        init_pattern = re.compile(r"^\s*(eval.*oh-my-posh init.*|oh-my-posh init.*fish.*)")
        config_pattern = re.compile(r"--config[=\s]['\"]*([^'\"]+)['\"]*")
        
        for line in lines:
            if init_pattern.search(line) and not line.strip().startswith('#'):
                config_match = config_pattern.search(line)
                if config_match:
                    theme_path = config_match.group(1)
                    theme_name = os.path.basename(theme_path).replace('.omp.json', '')
                    return theme_name
        return None
    except Exception:
        return None

def remove_theme(theme_name):
    """Removes a theme file from local storage and clears it from cache."""
    theme_path = os.path.join(THEMES_DIR, f"{theme_name}.omp.json")
    try:
        if os.path.exists(theme_path):
            os.remove(theme_path)
            # Remove from cache if present
            cache_key = _theme_cache._get_cache_key(theme_path)
            if cache_key in _theme_cache.cache:
                del _theme_cache.cache[cache_key]
            if cache_key in _theme_cache.file_timestamps:
                del _theme_cache.file_timestamps[cache_key]
            return True
        return False
    except Exception:
        return False

# --- Theme Metadata Cache ---

class ThemeMetadataCache:
    """Simple in-memory cache for theme metadata with LRU eviction and file modification tracking."""
    
    def __init__(self, max_size=MAX_CACHE_SIZE):
        self.max_size = max_size
        self.cache = OrderedDict()  # Maintains insertion order for LRU
        self.file_timestamps = {}   # Track file modification times
    
    def _get_cache_key(self, theme_path):
        """Generate cache key from theme path."""
        return os.path.abspath(theme_path)
    
    def _is_file_modified(self, theme_path):
        """Check if file has been modified since last cache."""
        try:
            current_mtime = os.path.getmtime(theme_path)
            cache_key = self._get_cache_key(theme_path)
            cached_mtime = self.file_timestamps.get(cache_key)
            return cached_mtime is None or current_mtime > cached_mtime
        except OSError:
            return True  # File doesn't exist or can't be accessed
    
    def get(self, theme_path):
        """Get cached metadata if available and file hasn't been modified."""
        if not os.path.exists(theme_path):
            return None
            
        cache_key = self._get_cache_key(theme_path)
        
        # Check if file has been modified
        if self._is_file_modified(theme_path):
            # File modified, remove from cache if present
            if cache_key in self.cache:
                del self.cache[cache_key]
                del self.file_timestamps[cache_key]
            return None
        
        # Check if we have cached data
        if cache_key in self.cache:
            # Move to end (most recently used)
            metadata = self.cache.pop(cache_key)
            self.cache[cache_key] = metadata
            return metadata
        
        return None
    
    def put(self, theme_path, metadata):
        """Store metadata in cache with LRU eviction."""
        if not os.path.exists(theme_path):
            return
            
        cache_key = self._get_cache_key(theme_path)
        
        # Remove oldest entries if cache is full
        while len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            if oldest_key in self.file_timestamps:
                del self.file_timestamps[oldest_key]
        
        # Store metadata and file timestamp
        try:
            self.cache[cache_key] = metadata
            self.file_timestamps[cache_key] = os.path.getmtime(theme_path)
        except OSError:
            pass  # Ignore if we can't get file timestamp
    
    def clear(self):
        """Clear all cached data."""
        self.cache.clear()
        self.file_timestamps.clear()
    
    def size(self):
        """Get current cache size."""
        return len(self.cache)

# Global cache instance
_theme_cache = ThemeMetadataCache()

# --- Theme Metadata Parser ---

def parse_theme_metadata(theme_path):
    """Extract metadata from .omp.json file with caching support.
    
    Args:
        theme_path (str): Path to the .omp.json theme file
        
    Returns:
        dict: Theme metadata with keys: 'name', 'segments', 'colors', 'description', 'complexity'
        Returns None if file cannot be parsed or doesn't exist
    """
    if not os.path.exists(theme_path):
        return None
    
    # Check cache first
    cached_metadata = _theme_cache.get(theme_path)
    if cached_metadata is not None:
        return cached_metadata
    
    try:
        with open(theme_path, 'r', encoding='utf-8') as f:
            theme_data = json.load(f)
        
        # Extract theme name from file path
        theme_name = os.path.basename(theme_path).replace('.omp.json', '')
        
        # Extract segments information
        segments = []
        segment_types = set()
        
        # Parse blocks and segments
        blocks = theme_data.get('blocks', [])
        for block in blocks:
            block_segments = block.get('segments', [])
            for segment in block_segments:
                segment_type = segment.get('type', 'unknown')
                segments.append(segment_type)
                segment_types.add(segment_type)
        
        # Extract color information
        colors = {}
        palette = theme_data.get('palette', {})
        if palette:
            colors.update(palette)
        
        # Look for common color properties in segments
        for block in blocks:
            block_segments = block.get('segments', [])
            for segment in block_segments:
                if 'background' in segment:
                    colors['segment_bg'] = segment['background']
                if 'foreground' in segment:
                    colors['segment_fg'] = segment['foreground']
                break  # Just get first segment colors as sample
        
        # Generate description based on segments
        description = _generate_description_from_segments(segment_types)
        
        # Determine complexity based on segment count
        complexity = _determine_complexity(len(segments))
        
        metadata = {
            'name': theme_name,
            'segments': list(segment_types),
            'colors': colors,
            'description': description,
            'complexity': complexity
        }
        
        # Cache the successfully parsed metadata
        _theme_cache.put(theme_path, metadata)
        return metadata
        
    except (json.JSONDecodeError, KeyError, IOError) as e:
        # Return basic info even if parsing fails
        theme_name = os.path.basename(theme_path).replace('.omp.json', '') if theme_path else 'unknown'
        fallback_metadata = {
            'name': theme_name,
            'segments': [],
            'colors': {},
            'description': 'Unable to parse theme file',
            'complexity': 'Unknown'
        }
        
        # Cache the fallback metadata to avoid repeated parsing attempts
        _theme_cache.put(theme_path, fallback_metadata)
        return fallback_metadata

def _generate_description_from_segments(segment_types):
    """Generate a description based on the segments present in the theme."""
    if not segment_types:
        return "Simple theme with basic prompt"
    
    key_segments = []
    if 'git' in segment_types:
        key_segments.append("Git integration")
    if 'path' in segment_types:
        key_segments.append("Path display")
    if 'time' in segment_types:
        key_segments.append("Time display")
    if 'battery' in segment_types:
        key_segments.append("Battery status")
    if 'python' in segment_types:
        key_segments.append("Python environment")
    if 'node' in segment_types:
        key_segments.append("Node.js version")
    
    if key_segments:
        return f"Features: {', '.join(key_segments[:3])}" + ("..." if len(key_segments) > 3 else "")
    else:
        return f"Custom theme with {len(segment_types)} segments"

def _determine_complexity(segment_count):
    """Determine theme complexity based on number of segments."""
    if segment_count <= 3:
        return "Simple"
    elif segment_count <= 6:
        return "Medium"
    else:
        return "Complex"

# Enhanced preview functionality moved to preview.py module
# This function is kept for backward compatibility but now uses the enhanced module
def generate_preview_text(metadata):
    """Generate displayable preview text from theme metadata.
    
    This function is deprecated. Use preview.show_enhanced_preview() instead.
    Kept for backward compatibility.
    """
    try:
        from .preview import _generate_enhanced_preview_content
    except ImportError:
        # Fallback for when running main.py directly
        from preview import _generate_enhanced_preview_content
    
    # Convert old metadata format to new format if needed
    if metadata and 'name' in metadata:
        enhanced_metadata = {
            'name': metadata.get('name', 'unknown'),
            'version': 'unknown',
            'source': 'unknown',
            'colors': metadata.get('colors', {})
        }
        return _generate_enhanced_preview_content(enhanced_metadata)
    
    return "Preview unavailable - theme data not found"

# --- Shell Configuration Logic ---

def get_shell_info():
    """Detects the user's shell and returns the config file path."""
    shell_path = os.environ.get("SHELL", "")
    shell_name = os.path.basename(shell_path)
    config_file = None
    if shell_name == "bash":
        config_file = os.path.expanduser("~/.bashrc")
    elif shell_name == "zsh":
        config_file = os.path.expanduser("~/.zshrc")
    elif shell_name == "fish":
        config_file = os.path.expanduser("~/.config/fish/config.fish")
    return shell_name, config_file

def update_shell_config(theme_name, shell, config_file):
    """Removes all existing Oh My Posh theme lines and activates the selected theme."""
    print(f"Activating theme '{theme_name}' in {os.path.basename(config_file)}...")
    local_theme_path = os.path.join(THEMES_DIR, f"{theme_name}.omp.json")

    if not os.path.exists(local_theme_path):
        print(f"Theme file not found: {local_theme_path}")
        if not download_theme(theme_name):
            return False # Stop if download fails

    init_command = f"eval $(oh-my-posh init {shell} --config '{local_theme_path}')"
    if shell == 'fish':
        init_command = f"oh-my-posh init {shell} --config '{local_theme_path}' | source"

    try:
        with open(config_file, "r") as f:
            lines = f.readlines()

        final_lines = []
        init_pattern = re.compile(r"^\s*(eval.*oh-my-posh init.*|oh-my-posh init.*fish.*)")

        # Remove all Oh My Posh lines (both active and commented)
        for line in lines:
            if init_pattern.search(line):
                pass  # Skip all Oh My Posh lines
            else:
                final_lines.append(line)

        # Clean up trailing empty lines
        while final_lines and final_lines[-1].strip() == "":
            final_lines.pop()

        # Add the new active command
        final_lines.append(f"{init_command}\n")

        with open(config_file, "w") as f:
            f.writelines(final_lines)
        return True
    except Exception as e:
        print(f"Error updating config file: {e}")
        return False

def download_theme(theme_name):
    """Downloads a single theme file from official or custom repositories."""
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
    
    theme_filename = f"{theme_name}.omp.json"
    local_theme_path = os.path.join(THEMES_DIR, theme_filename)

    print(f"Downloading '{theme_name}'...")
    
    # Try official repository first
    theme_url = f"https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/{theme_filename}"
    try:
        request.urlretrieve(theme_url, local_theme_path)
        return True
    except Exception:
        pass  # Try custom repositories
    
    # Try custom repositories
    try:
        from .config import get_custom_repositories
        from .repositories import fetch_themes_from_repo, install_custom_themes
    except ImportError:
        # Fallback for when running main.py directly
        from config import get_custom_repositories
        from repositories import fetch_themes_from_repo, install_custom_themes
    
    custom_repos = get_custom_repositories()
    for repo_url in custom_repos:
        try:
            theme_files, error_msg = fetch_themes_from_repo(repo_url)
            if not error_msg and theme_files:
                # Find the specific theme in this repository
                matching_theme = None
                for theme_file in theme_files:
                    if theme_file['name'].replace('.omp.json', '') == theme_name:
                        matching_theme = theme_file
                        break
                
                if matching_theme:
                    # Install just this one theme
                    success_count, errors = install_custom_themes([matching_theme], repo_url, THEMES_DIR)
                    if success_count > 0:
                        return True
        except Exception:
            continue  # Try next repository
    
    print(f"Error downloading theme: Theme '{theme_name}' not found in any repository")
    return False

def download_theme_for_preview(theme_name):
    """Downloads a theme file silently for preview purposes from any repository."""
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
    
    theme_filename = f"{theme_name}.omp.json"
    local_theme_path = os.path.join(THEMES_DIR, theme_filename)

    # Try official repository first
    theme_url = f"https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/{theme_filename}"
    try:
        request.urlretrieve(theme_url, local_theme_path)
        return True
    except Exception:
        pass  # Try custom repositories
    
    # Try custom repositories
    try:
        from .config import get_custom_repositories
        from .repositories import fetch_themes_from_repo, install_custom_themes
    except ImportError:
        # Fallback for when running main.py directly
        from config import get_custom_repositories
        from repositories import fetch_themes_from_repo, install_custom_themes
    
    custom_repos = get_custom_repositories()
    for repo_url in custom_repos:
        try:
            theme_files, error_msg = fetch_themes_from_repo(repo_url)
            if not error_msg and theme_files:
                # Find the specific theme in this repository
                matching_theme = None
                for theme_file in theme_files:
                    if theme_file['name'].replace('.omp.json', '') == theme_name:
                        matching_theme = theme_file
                        break
                
                if matching_theme:
                    # Install just this one theme silently
                    success_count, errors = install_custom_themes([matching_theme], repo_url, THEMES_DIR)
                    if success_count > 0:
                        return True
        except Exception:
            continue  # Try next repository
    
    return False

def get_theme_metadata_optimized(theme_name, is_local=False):
    """Get theme metadata with optimized file reuse and caching.
    
    Args:
        theme_name (str): Name of the theme
        is_local (bool): Whether this is a local theme or remote theme
        
    Returns:
        tuple: (metadata_dict, was_downloaded_for_preview)
        metadata_dict: Theme metadata or None if unavailable
        was_downloaded_for_preview: True if theme was downloaded just for this preview
    """
    local_theme_path = os.path.join(THEMES_DIR, f"{theme_name}.omp.json")
    
    if os.path.exists(local_theme_path):
        # Theme file exists locally, parse it (with caching)
        metadata = parse_theme_metadata(local_theme_path)
        return metadata, False
    elif not is_local:
        # Remote theme not downloaded yet, download for preview
        if download_theme_for_preview(theme_name):
            metadata = parse_theme_metadata(local_theme_path)
            return metadata, True
        else:
            return None, False
    else:
        # Local theme file missing
        return None, False

def clear_theme_cache():
    """Clear the theme metadata cache. Useful for testing or memory management."""
    _theme_cache.clear()

def get_cache_stats():
    """Get cache statistics for debugging/monitoring.
    
    Returns:
        dict: Cache statistics including size and max_size
    """
    return {
        'size': _theme_cache.size(),
        'max_size': _theme_cache.max_size,
        'hit_ratio': 'N/A'  # Could be implemented with hit/miss counters if needed
    }

# --- Curses UI ---

def draw_panel(win, title, items, selection_idx, scroll_top, is_active, selected_items=None, active_theme=None):
    """Draws a single panel window."""
    win.clear()
    border_color = curses.color_pair(2) if is_active else curses.color_pair(1)
    win.attron(border_color)
    win.box()
    win.attroff(border_color)

    win.addstr(0, 2, f" {title} ", curses.A_BOLD)
    
    h, w = win.getmaxyx()
    menu_height = h - 2
    
    for i in range(menu_height):
        list_idx = scroll_top + i
        if list_idx < len(items):
            item_name = items[list_idx]
            
            # Add checkbox for remote themes or active marker for local themes
            prefix = ""
            if selected_items is not None:  # Remote themes
                prefix = "[✓] " if item_name in selected_items else "[ ] "
            elif active_theme and item_name == active_theme:  # Local themes - mark active
                prefix = "★ "
            
            display_name = prefix + item_name
            if len(display_name) >= w - 4:
                display_name = display_name[:w - 5] + "…"
            
            if list_idx == selection_idx:
                win.attron(curses.color_pair(3) if is_active else curses.color_pair(1))
                win.addstr(i + 1, 2, display_name)
                win.attroff(curses.color_pair(3) if is_active else curses.color_pair(1))
            else:
                win.addstr(i + 1, 2, display_name)
    win.refresh()

def show_confirmation(stdscr, message):
    """Shows a confirmation dialog and returns True for Y, False for N."""
    h, w = stdscr.getmaxyx()
    dialog_h, dialog_w = 5, min(len(message) + 10, w - 4)
    dialog_y = h // 2 - dialog_h // 2
    dialog_x = w // 2 - dialog_w // 2
    
    dialog = curses.newwin(dialog_h, dialog_w, dialog_y, dialog_x)
    dialog.attron(curses.color_pair(2))
    dialog.box()
    dialog.attroff(curses.color_pair(2))
    
    dialog.addstr(1, 2, message[:dialog_w - 4])
    dialog.addstr(3, 2, "Press y/n:")
    dialog.refresh()
    
    while True:
        key = dialog.getch()
        if key in [ord('y'), ord('Y')]:
            return True
        elif key in [ord('n'), ord('N')]:
            return False

def show_keep_theme_dialog(stdscr, theme_name):
    """Shows a dialog asking whether to keep the downloaded theme."""
    h, w = stdscr.getmaxyx()
    message = f"Keep downloaded theme '{theme_name}'?"
    dialog_h, dialog_w = 6, min(len(message) + 10, w - 4)
    dialog_y = h // 2 - dialog_h // 2
    dialog_x = w // 2 - dialog_w // 2
    
    dialog = curses.newwin(dialog_h, dialog_w, dialog_y, dialog_x)
    dialog.attron(curses.color_pair(2))
    dialog.box()
    dialog.attroff(curses.color_pair(2))
    
    dialog.addstr(1, 2, message[:dialog_w - 4])
    dialog.addstr(2, 2, "y - Keep")
    dialog.addstr(3, 2, "n - Remove")
    dialog.addstr(4, 2, "Press Y/N:")
    dialog.refresh()
    
    while True:
        key = dialog.getch()
        if key in [ord('y'), ord('Y')]:
            return True
        elif key in [ord('n'), ord('N')]:
            return False

def show_theme_preview(stdscr, theme_name, metadata, downloaded_for_preview=False):
    """Shows a theme preview dialog with enhanced metadata and sample prompts.
    
    Args:
        stdscr: The curses screen object
        theme_name (str): Name of the theme to preview
        metadata (dict): Theme metadata (legacy parameter, now unused)
        downloaded_for_preview (bool): Whether theme was downloaded just for preview
        
    Returns:
        bool: True if user wants to keep downloaded theme, False otherwise
    """
    try:
        from .preview import show_enhanced_preview
    except ImportError:
        # Fallback for when running main.py directly
        from preview import show_enhanced_preview
    
    # Use the enhanced preview functionality
    # Determine if this is a local theme based on whether it was downloaded for preview
    is_local = not downloaded_for_preview
    
    return show_enhanced_preview(stdscr, theme_name, is_local)

def show_status_message(stdscr, message, duration=2):
    """Shows a temporary status message."""
    h, w = stdscr.getmaxyx()
    dialog_h, dialog_w = 3, min(len(message) + 4, w - 4)
    dialog_y = h // 2 - dialog_h // 2
    dialog_x = w // 2 - dialog_w // 2
    
    dialog = curses.newwin(dialog_h, dialog_w, dialog_y, dialog_x)
    dialog.attron(curses.color_pair(2))
    dialog.box()
    dialog.attroff(curses.color_pair(2))
    
    dialog.addstr(1, 2, message[:dialog_w - 4])
    dialog.refresh()
    
    curses.napms(duration * 1000)  # Sleep for duration seconds

def wrap_status_line(status_text, width, max_lines=2):
    """Wraps status line text to fit within terminal width across multiple lines.
    
    Args:
        status_text (str): The full status line text
        width (int): Available width for the status line
        max_lines (int): Maximum number of lines to use
        
    Returns:
        list: List of wrapped lines
    """
    if len(status_text) <= width:
        return [status_text]
    
    # Split by separators and try to wrap intelligently
    parts = status_text.split(' | ')
    lines = []
    current_line = ""
    
    for i, part in enumerate(parts):
        # Check if adding this part would exceed width
        separator = " | " if current_line else ""
        test_line = current_line + separator + part
        
        if len(test_line) <= width:
            current_line = test_line
        else:
            # Current line is full, start a new one
            if current_line:
                lines.append(current_line)
                current_line = part
            else:
                # Single part is too long, truncate it
                current_line = part[:width-3] + "..."
        
        # If we've reached max lines, truncate remaining parts
        if len(lines) >= max_lines - 1:
            if current_line:
                # Add remaining parts to current line if space allows
                remaining_parts = parts[i+1:]
                if remaining_parts:
                    remaining_text = " | " + " | ".join(remaining_parts)
                    available_space = width - len(current_line)
                    if available_space > 6:  # Minimum space for "... | x"
                        truncated_remaining = remaining_text[:available_space-3] + "..."
                        current_line += truncated_remaining
                lines.append(current_line)
            break
    
    # Add the last line if it wasn't added yet
    if current_line and len(lines) < max_lines:
        lines.append(current_line)
    
    return lines

def show_action_choice(stdscr, theme_name):
    """Shows a dialog to choose between Activate, Remove, or Customize for local themes."""
    h, w = stdscr.getmaxyx()
    dialog_h, dialog_w = 8, min(50, w - 4)
    dialog_y = h // 2 - dialog_h // 2
    dialog_x = w // 2 - dialog_w // 2
    
    dialog = curses.newwin(dialog_h, dialog_w, dialog_y, dialog_x)
    dialog.attron(curses.color_pair(2))
    dialog.box()
    dialog.attroff(curses.color_pair(2))
    
    dialog.addstr(1, 2, f"Theme: {theme_name}"[:dialog_w - 4])
    dialog.addstr(3, 2, "(a) - Activate theme")
    dialog.addstr(4, 2, "(r) - Remove theme")
    dialog.addstr(5, 2, "(c) - Customize colors")
    dialog.addstr(6, 2, "(ESC) - Cancel")
    dialog.refresh()
    
    while True:
        key = dialog.getch()
        if key in [ord('a'), ord('A')]:
            return "activate"
        elif key in [ord('r'), ord('R')]:
            return "remove"
        elif key in [ord('c'), ord('C')]:
            return "customize"
        elif key == 27:  # ESC
            return "cancel"

def main_ui(stdscr):
    """The main application UI logic, wrapped by curses."""
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK) # Default
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Active border
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Active selection

    # Initial data fetch
    local_themes = get_local_themes()
    remote_themes = fetch_remote_themes()
    selected_for_install = set()  # Themes selected for installation

    # Search state
    search_state = {
        'active': False,
        'query': '',
        'filtered_local': local_themes,
        'filtered_remote': remote_themes
    }

    # State
    panels = [local_themes, remote_themes]
    selections = [0, 0]
    scroll_tops = [0, 0]
    active_panel_idx = 0

    shell, config_file = get_shell_info()
    active_theme = get_active_theme(config_file)

    # Initialize panel variables
    local_panel = None
    remote_panel = None
    panel_wins = []
    last_status_height = 0

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()
        
        status_line = "(TAB): switch | (Enter): activate/remove/select | (SPACE): toggle | (p): preview | (i): install selected | (/): search | (+): add repo | (q): quit"
        if selected_for_install:
            status_line += f" | Selected: {len(selected_for_install)}"
        if search_state['active']:
            status_line += f" | Search: {search_state['query'][:10]}{'...' if len(search_state['query']) > 10 else ''}"
        
        # Wrap status line to fit terminal width
        status_lines = wrap_status_line(status_line, w - 4)
        current_status_height = len(status_lines)
        
        # Display status lines
        for i, line in enumerate(status_lines):
            stdscr.addstr(i, 2, line, curses.A_REVERSE)
        
        # Recreate panels if status height changed or panels don't exist
        if current_status_height != last_status_height or not panel_wins:
            panel_width = w // 2
            local_panel = curses.newwin(h - current_status_height - 1, panel_width, current_status_height, 0)
            remote_panel = curses.newwin(h - current_status_height - 1, w - panel_width, current_status_height, panel_width)
            panel_wins = [local_panel, remote_panel]
            last_status_height = current_status_height
        
        stdscr.refresh()

        # Use filtered lists if search is active
        current_local = search_state['filtered_local'] if search_state['active'] else local_themes
        current_remote = search_state['filtered_remote'] if search_state['active'] else remote_themes
        current_panels = [current_local, current_remote]

        # Handle scrolling for the active panel
        active_list = current_panels[active_panel_idx]
        if active_list:  # Only handle scrolling if list is not empty
            h_panel, w_panel = panel_wins[active_panel_idx].getmaxyx()
            menu_height = h_panel - 2
            if selections[active_panel_idx] < scroll_tops[active_panel_idx]:
                scroll_tops[active_panel_idx] = selections[active_panel_idx]
            elif selections[active_panel_idx] >= scroll_tops[active_panel_idx] + menu_height:
                scroll_tops[active_panel_idx] = selections[active_panel_idx] - menu_height + 1

        # Draw panels with search highlighting
        search_query = search_state['query'] if search_state['active'] else None
        draw_panel_with_search(local_panel, "Local Themes", current_local, selections[0], scroll_tops[0], 
                              active_panel_idx == 0, active_theme=active_theme, search_query=search_query)
        draw_panel_with_search(remote_panel, "Remote Themes", current_remote, selections[1], scroll_tops[1], 
                              active_panel_idx == 1, selected_for_install, search_query=search_query)

        key = stdscr.getch()

        if key == ord('q') or key == ord('Q'):
            return

        elif key == 9:  # TAB
            active_panel_idx = 1 - active_panel_idx

        elif key == curses.KEY_UP:
            if active_list and selections[active_panel_idx] > 0:
                selections[active_panel_idx] -= 1
        
        elif key == curses.KEY_DOWN:
            if active_list and selections[active_panel_idx] < len(active_list) - 1:
                selections[active_panel_idx] += 1

        elif key == ord('/'):  # Search mode
            search_result = handle_search_mode(stdscr, local_themes, remote_themes)
            if search_result:
                search_state.update(search_result)
                # Reset selections to 0 when entering search mode
                selections = [0, 0]
                scroll_tops = [0, 0]
            else:
                # Search cancelled, clear search state
                search_state = {
                    'active': False,
                    'query': '',
                    'filtered_local': local_themes,
                    'filtered_remote': remote_themes
                }
                selections = [0, 0]
                scroll_tops = [0, 0]

        elif key == ord('+'):  # Add custom repository
            success, message = handle_add_repository(stdscr, THEMES_DIR)
            if success:
                # Refresh local themes list
                local_themes = get_local_themes()
                panels[0] = local_themes
                # Update search state if active
                if search_state['active']:
                    search_state['filtered_local'] = filter_themes(local_themes, search_state['query'])
            show_status_message(stdscr, message)

        elif key == ord(' '):  # SPACE - toggle selection for remote themes
            if active_panel_idx == 1 and current_remote:
                selected_theme = current_remote[selections[1]]
                if selected_theme in selected_for_install:
                    selected_for_install.remove(selected_theme)
                else:
                    selected_for_install.add(selected_theme)

        elif key == ord('i') or key == ord('I'):  # Install selected themes
            if selected_for_install:
                if show_confirmation(stdscr, f"Install {len(selected_for_install)} theme(s)?"):
                    installed_count = 0
                    for theme in list(selected_for_install):
                        if download_theme(theme):
                            installed_count += 1
                            selected_for_install.remove(theme)
                    
                    # Refresh local themes list
                    local_themes = get_local_themes()
                    panels[0] = local_themes
                    
                    # Update search state if active
                    if search_state['active']:
                        search_state['filtered_local'] = filter_themes(local_themes, search_state['query'])
                    
                    show_status_message(stdscr, f"Installed {installed_count} theme(s)!")
            else:
                show_status_message(stdscr, "No themes selected for installation")

        elif key == ord('p') or key == ord('P'):  # Preview theme
            current_list = current_panels[active_panel_idx]
            if not current_list:
                show_status_message(stdscr, "No themes available to preview")
            else:
                selected_theme = current_list[selections[active_panel_idx]]
                is_local_theme = (active_panel_idx == 0)
                
                if is_local_theme:
                    # For local themes, use optimized metadata retrieval
                    metadata, was_downloaded = get_theme_metadata_optimized(selected_theme, is_local=True)
                    if metadata:
                        show_theme_preview(stdscr, selected_theme, metadata, downloaded_for_preview=False)
                    else:
                        show_status_message(stdscr, f"Preview unavailable - could not read theme file")
                
                else:  # Remote theme
                    # Check if theme already exists locally
                    local_theme_path = os.path.join(THEMES_DIR, f"{selected_theme}.omp.json")
                    
                    if os.path.exists(local_theme_path):
                        # Theme already downloaded, just show preview
                        show_theme_preview(stdscr, selected_theme, None, downloaded_for_preview=False)
                    else:
                        # Ask permission before downloading
                        if show_confirmation(stdscr, f"Download '{selected_theme}' for preview?"):
                            # User agreed to download, show preview (it will handle download and keep/remove dialog)
                            keep_theme = show_theme_preview(stdscr, selected_theme, None, downloaded_for_preview=True)
                            
                            if keep_theme:
                                # User wants to keep the theme, refresh local themes list
                                local_themes = get_local_themes()
                                panels[0] = local_themes
                                
                                # Update search state if active
                                if search_state['active']:
                                    search_state['filtered_local'] = filter_themes(local_themes, search_state['query'])
                                
                                show_status_message(stdscr, f"Theme '{selected_theme}' downloaded and kept!")
                            else:
                                # User wants to remove the theme
                                if remove_theme(selected_theme):
                                    show_status_message(stdscr, f"Theme '{selected_theme}' downloaded but removed!")
                                else:
                                    show_status_message(stdscr, f"Failed to remove downloaded theme '{selected_theme}'")
                        else:
                            show_status_message(stdscr, f"Preview cancelled for '{selected_theme}'")

        elif key == curses.KEY_ENTER or key in [10, 13]:
            if active_panel_idx == 0 and current_local:  # Local theme - show action choice
                selected_theme = current_local[selections[0]]
                action = show_action_choice(stdscr, selected_theme)
                
                if action == "activate":
                    if show_confirmation(stdscr, f"Activate theme '{selected_theme}'?"):
                        if update_shell_config(selected_theme, shell, config_file):
                            active_theme = selected_theme  # Update active theme
                            show_status_message(stdscr, f"Theme '{selected_theme}' activated!")
                        else:
                            show_status_message(stdscr, "Failed to activate theme")
                
                elif action == "remove":
                    if show_confirmation(stdscr, f"This will permanently remove {selected_theme}.omp.json file"):
                        if remove_theme(selected_theme):
                            # Refresh local themes list
                            local_themes = get_local_themes()
                            panels[0] = local_themes
                            
                            # Update search state if active
                            if search_state['active']:
                                search_state['filtered_local'] = filter_themes(local_themes, search_state['query'])
                                current_local = search_state['filtered_local']
                            else:
                                current_local = local_themes
                            
                            # Adjust selection if needed
                            if selections[0] >= len(current_local) and current_local:
                                selections[0] = len(current_local) - 1
                            elif not current_local:
                                selections[0] = 0
                            
                            # Update active theme if we removed the active one
                            if active_theme == selected_theme:
                                active_theme = get_active_theme(config_file)
                            
                            show_status_message(stdscr, f"Theme '{selected_theme}' removed!")
                        else:
                            show_status_message(stdscr, "Failed to remove theme")
                
                elif action == "customize":
                    # Import editor module
                    try:
                        from .editor import show_color_editor, _show_save_options_dialog, save_theme_changes
                    except ImportError:
                        # Fallback for when running main.py directly
                        from editor import show_color_editor, _show_save_options_dialog, save_theme_changes
                    
                    theme_path = os.path.join(THEMES_DIR, f"{selected_theme}.omp.json")
                    
                    # Show color editor
                    modified_theme_data = show_color_editor(stdscr, theme_path)
                    
                    if modified_theme_data is not None:
                        # Show save options dialog
                        new_name, overwrite = _show_save_options_dialog(stdscr, selected_theme)
                        
                        if overwrite or new_name:
                            success, result_path_or_error = save_theme_changes(
                                modified_theme_data, theme_path, new_name
                            )
                            
                            if success:
                                if new_name:
                                    # Refresh local themes list to show new theme
                                    local_themes = get_local_themes()
                                    panels[0] = local_themes
                                    
                                    # Update search state if active
                                    if search_state['active']:
                                        search_state['filtered_local'] = filter_themes(local_themes, search_state['query'])
                                        current_local = search_state['filtered_local']
                                    else:
                                        current_local = local_themes
                                    
                                    show_status_message(stdscr, f"Theme saved as '{new_name}'!")
                                else:
                                    show_status_message(stdscr, f"Theme '{selected_theme}' updated!")
                            else:
                                show_status_message(stdscr, f"Error: {result_path_or_error}")
                        else:
                            show_status_message(stdscr, "Customization cancelled")
                    else:
                        show_status_message(stdscr, "Color editing cancelled")

def main():
    """Main entry point for the oh-my-theme application."""
    shell, config_file = get_shell_info()
    if not shell:
        print("Unsupported shell or shell not detected. Exiting.")
        sys.exit(1)

    try:
        curses.wrapper(main_ui)
    except curses.error as e:
        print(f"Curses error: {e}")
    except (KeyboardInterrupt, EOFError):
        pass # Exit gracefully
    
    # Create stylized terminal output with ASCII box
    box_width = 70
    print("\n" + "#" * box_width)
    print("#" + " " * (box_width - 2) + "#")
    print("#" + " Like oh-my-theme?".center(box_width - 2) + "#")
    print("#" + " Give it a 🌟 https://github.com/mikeisfree/oh-my-theme".center(box_width - 2) + "#")
    print("#" + " " * (box_width - 2) + "#")
    print("%" * box_width)
    print("%" + " " * (box_width - 2) + "%")
    print("%" + " Remember to reload your shell to see theme changes:".center(box_width - 2) + "%")
    print("%" + " " * (box_width - 2) + "%")
    print("%" + f" >>> Run: source ~/{os.path.basename(config_file)} <<<".center(box_width - 2) + "%")
    print("%" + " " * (box_width - 2) + "%")
    print("%" * box_width)

if __name__ == "__main__":
    main()