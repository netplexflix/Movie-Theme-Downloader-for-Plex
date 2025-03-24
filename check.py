import os
import yaml
import sys
from plexapi.server import PlexServer
import time

# ANSI color codes for better readability
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(text, color):
    """Print text in color"""
    color_code = getattr(Colors, color.upper(), '')
    print(f"{color_code}{text}{Colors.ENDC}")

def load_config():
    """Load configuration from config.yml"""
    try:
        with open('config.yml', 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print_colored(f"Error loading config: {e}", 'red')
        exit(1)

def map_path(path, path_mappings):
    """Map remote paths to local paths based on config"""
    for remote, local in path_mappings.items():
        if path.startswith(remote):
            return path.replace(remote, local)
    return path

def get_plex_movies(config):
    """Connect to Plex and get all movies"""
    try:
        print_colored("Connecting to Plex server...", 'blue')
        plex = PlexServer(config['PLEX_URL'], config['PLEX_TOKEN'])
        
        print_colored(f"Connected to {plex.friendlyName}", 'green')
        print_colored(f"Accessing movie library: {config['MOVIE_LIBRARY_NAME']}", 'blue')
        
        movie_library = plex.library.section(config['MOVIE_LIBRARY_NAME'])
        movies = movie_library.all()
        
        print_colored(f"Successfully retrieved {len(movies)} movies from Plex", 'green')
        return movies, plex
    except Exception as e:
        print_colored(f"Error connecting to Plex: {e}", 'red')
        exit(1)

def has_theme_metadata(movie):
    """Check if the movie has 'theme=' mentioned in metadata"""
    try:
        # Check if the movie has the 'theme' attribute
        if hasattr(movie, 'theme') and movie.theme:
            return True
            
        # Check in the XML data if available
        if hasattr(movie, '_data') and movie._data:
            xml_str = str(movie._data)
            if 'theme=' in xml_str or '<theme>' in xml_str:
                return True
        
        # Safely check various attributes
        safe_attrs = ['summary', 'title', 'originalTitle', 'titleSort']
        for attr in safe_attrs:
            if hasattr(movie, attr) and getattr(movie, attr):
                if 'theme=' in str(getattr(movie, attr)):
                    return True
        
        # Check in available fields
        if hasattr(movie, 'fields'):
            for field in movie.fields:
                if field and 'theme=' in str(field):
                    return True
        
        # Check in available tags
        try:
            if hasattr(movie, 'genres'):
                for genre in movie.genres:
                    if genre and 'theme=' in str(genre.tag):
                        return True
        except:
            pass
            
        try:
            if hasattr(movie, 'collections'):
                for collection in movie.collections:
                    if collection and 'theme=' in str(collection.tag):
                        return True
        except:
            pass
            
        try:
            if hasattr(movie, 'labels'):
                for label in movie.labels:
                    if label and 'theme=' in str(label):
                        return True
        except:
            pass
        
        return False
    except Exception as e:
        print_colored(f"Error checking theme metadata for '{movie.title}': {str(e)}", 'red')
        return False

def analyze_theme_files_and_metadata(movies, path_mappings):
    """Analyze which movies have theme files and theme metadata"""
    theme_file_with_metadata = []
    theme_file_without_metadata = []
    movies_without_theme = []  # New list to track movies without theme files
    errors = []
    
    print_colored("\nAnalyzing theme files and metadata...", 'blue')
    total = len(movies)
    
    # Print initial progress
    print(f"Processing movie: 0/{total}", end='', flush=True)
    
    for i, movie in enumerate(movies):
        # Update progress in place
        print(f"\rProcessing movie: {i+1}/{total}", end='', flush=True)
            
        try:
            title = movie.title
            year = str(movie.year) if movie.year else "Unknown Year"
            
            # Get the movie's file path and map it if needed
            if not movie.locations:
                movies_without_theme.append((title, year, movie))  # Add to list without theme
                continue
                
            movie_path = movie.locations[0]
            local_path = map_path(movie_path, path_mappings)
            
            # The theme file should be in the same directory as the movie
            theme_path = os.path.join(os.path.dirname(local_path), "theme.mp3")
            
            # Check if theme.mp3 exists and is not empty
            if os.path.exists(theme_path) and os.path.getsize(theme_path) > 0:
                # Check if theme metadata exists
                has_metadata = has_theme_metadata(movie)
                
                file_size = os.path.getsize(theme_path) / 1024  # Size in KB
                
                if has_metadata:
                    theme_file_with_metadata.append((title, year, theme_path, file_size, movie))
                else:
                    theme_file_without_metadata.append((title, year, theme_path, file_size, movie))
            else:
                movies_without_theme.append((title, year, movie))  # Add to list without theme
        except Exception as e:
            error_msg = f"Error analyzing '{movie.title if hasattr(movie, 'title') else 'Unknown'}': {str(e)}"
            # Don't print errors immediately to avoid messing up the progress line
            errors.append(error_msg)
            movies_without_theme.append((movie.title if hasattr(movie, 'title') else 'Unknown', 
                                         str(movie.year) if hasattr(movie, 'year') and movie.year else "Unknown Year", 
                                         movie))
    
    # Print a newline after progress is complete
    print()
    
    # Now print any errors that occurred
    if errors:
        print_colored("\nErrors encountered during analysis:", 'red')
        for error in errors[:5]:  # Show only first 5 errors to avoid cluttering the console
            print_colored(f"  {error}", 'red')
        if len(errors) > 5:
            print_colored(f"  ... and {len(errors) - 5} more errors (see theme_analysis_errors.txt for full list)", 'red')
    
    return theme_file_with_metadata, theme_file_without_metadata, movies_without_theme, len(movies_without_theme), errors

def delete_theme_files(theme_files_to_delete, plex):
    """Delete theme.mp3 files from the provided list and refresh metadata"""
    deleted_count = 0
    error_count = 0
    refresh_count = 0
    refresh_errors = 0
    deletion_log = []
    
    print_colored("\nDeleting theme.mp3 files...", 'yellow')
    total = len(theme_files_to_delete)
    
    # Print initial progress
    print(f"Deleting file: 0/{total}", end='', flush=True)
    
    for i, (title, year, theme_path, size, movie) in enumerate(theme_files_to_delete):
        # Update progress in place
        print(f"\rDeleting file: {i+1}/{total}", end='', flush=True)
        
        try:
            if os.path.exists(theme_path):
                os.remove(theme_path)
                log_entry = f"Deleted: {title} ({year}) - {theme_path}"
                deletion_log.append(log_entry)
                deleted_count += 1
                
                # Attempt to refresh metadata
                try:
                    if hasattr(movie, 'refresh'):
                        movie.refresh()
                        refresh_count += 1
                        log_entry += " (metadata refreshed)"
                    else:
                        # Alternative method using ratingKey as in TDFP.py
                        if hasattr(movie, 'ratingKey'):
                            item = plex.fetchItem(movie.ratingKey)
                            item.refresh()
                            refresh_count += 1
                            log_entry += " (metadata refreshed)"
                        else:
                            log_entry += " (metadata refresh failed - no ratingKey)"
                            refresh_errors += 1
                except Exception as e:
                    log_entry += f" (metadata refresh error: {str(e)})"
                    refresh_errors += 1
            else:
                log_entry = f"File not found: {title} ({year}) - {theme_path}"
                deletion_log.append(log_entry)
                error_count += 1
        except Exception as e:
            log_entry = f"Error deleting: {title} ({year}) - {theme_path} - Error: {str(e)}"
            deletion_log.append(log_entry)
            error_count += 1
    
    # Print a newline after progress is complete
    print()
    
    # Save deletion log
    with open("theme_deletion_log.txt", "w", encoding="utf-8") as f:
        f.write("THEME.MP3 DELETION LOG\n")
        f.write("=====================\n\n")
        f.write(f"Total files processed: {len(theme_files_to_delete)}\n")
        f.write(f"Successfully deleted: {deleted_count}\n")
        f.write(f"Metadata refreshed: {refresh_count}\n")
        f.write(f"Metadata refresh errors: {refresh_errors}\n")
        f.write(f"Deletion errors: {error_count}\n\n")
        f.write("DETAILED LOG:\n")
        f.write("------------\n\n")
        for entry in deletion_log:
            f.write(f"{entry}\n")
    
    return deleted_count, error_count, refresh_count, refresh_errors

def main():
    print_colored("Plex Movie Theme File and Metadata Analyzer", 'header')
    
    # Load configuration
    config = load_config()
    path_mappings = config.get('PATH_MAPPINGS', {})
    
    # Get movies from Plex
    movies, plex = get_plex_movies(config)
    
    # Analyze theme files and metadata
    theme_with_meta, theme_without_meta, movies_without_theme, count_no_theme, errors = analyze_theme_files_and_metadata(movies, path_mappings)
    
    # Display results
    print_colored("\n=== SUMMARY ===", 'header')
    print_colored(f"Total movies checked: {len(movies)}", 'blue')
    print_colored(f"Movies without theme.mp3: {count_no_theme}", 'yellow')
    print_colored(f"Movies with theme detected in metadata: {len(theme_with_meta)}", 'green')
    print_colored(f"Movies with theme.mp3 but not detected in metadata: {len(theme_without_meta)}", 'red')
    print_colored(f"Errors encountered: {len(errors)}", 'red')
    
    # Save results to files
    print_colored("\nSaving results to files...", 'blue')
    
    with open("theme_with_metadata.txt", "w", encoding="utf-8") as f:
        f.write("MOVIES WITH THEME.MP3 AND THEME= METADATA\n")
        f.write("========================================\n\n")
        for title, year, path, size, _ in sorted(theme_with_meta, key=lambda x: x[0].lower()):
            f.write(f"{title} ({year}) - {size:.2f} KB\n")
    
    with open("theme_without_metadata.txt", "w", encoding="utf-8") as f:
        f.write("MOVIES WITH THEME.MP3 BUT NO THEME= METADATA\n")
        f.write("===========================================\n\n")
        for title, year, path, size, _ in sorted(theme_without_meta, key=lambda x: x[0].lower()):
            f.write(f"{title} ({year}) - {size:.2f} KB\n")
    
    with open("movies_without_theme_file.txt", "w", encoding="utf-8") as f:
        f.write("MOVIES WITHOUT THEME.MP3 FILES\n")
        f.write("==============================\n\n")
        for title, year, _ in sorted(movies_without_theme, key=lambda x: x[0].lower()):
            f.write(f"{title} ({year})\n")
    
    if errors:
        with open("theme_analysis_errors.txt", "w", encoding="utf-8") as f:
            f.write("ERRORS ENCOUNTERED DURING ANALYSIS\n")
            f.write("==================================\n\n")
            for error in errors:
                f.write(f"{error}\n")
        print_colored("- theme_analysis_errors.txt", 'red')
    
    print_colored("\nResults saved to:", 'green')
    print_colored("- theme_with_metadata.txt", 'yellow')
    print_colored("- theme_without_metadata.txt", 'yellow')
    print_colored("- movies_without_theme_file.txt", 'yellow')
    
    # Ask user if they want to delete theme.mp3 files without metadata
    if theme_without_meta:
        print_colored(f"\nFound {len(theme_without_meta)} theme.mp3 files without theme= metadata.", 'yellow')
        print_colored("These are the files that will be deleted if you proceed:", 'yellow')
        
        # Show sample of files to be deleted (max 10)
        sample_size = min(10, len(theme_without_meta))
        for i in range(sample_size):
            title, year, path, _, _ = theme_without_meta[i]
            print_colored(f"  - {title} ({year})", 'yellow')
        
        if len(theme_without_meta) > sample_size:
            print_colored(f"  - ... and {len(theme_without_meta) - sample_size} more (see theme_without_metadata.txt for full list)", 'yellow')
        
        print_colored(f"\nWARNING: This will permanently delete {len(theme_without_meta)} theme.mp3 files and refresh metadata!", 'red')
        user_response = input(f"{Colors.BOLD}Do you want to delete these theme.mp3 files? (yes/no):{Colors.ENDC} ").strip().lower()
        
        if user_response == 'yes':
            deleted_count, error_count, refresh_count, refresh_errors = delete_theme_files(theme_without_meta, plex)
            print_colored(f"\nDeletion complete:", 'green')
            print_colored(f"- Successfully deleted: {deleted_count} files", 'green')
            print_colored(f"- Metadata refreshed: {refresh_count} movies", 'green')
            print_colored(f"- Metadata refresh errors: {refresh_errors}", 'yellow' if refresh_errors > 0 else 'green')
            print_colored(f"- Deletion errors: {error_count}", 'yellow' if error_count > 0 else 'green')
            print_colored("See theme_deletion_log.txt for details.", 'blue')
        else:
            print_colored("\nDeletion cancelled. No files were deleted.", 'blue')
    else:
        print_colored("\nAll theme files are correctly picked up by Plex.", 'green')
    
    print_colored("\nScript execution complete.", 'header')

if __name__ == "__main__":
    main()