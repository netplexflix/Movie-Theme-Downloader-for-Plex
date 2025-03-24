import os
import sys
import yaml
import re
import gdown
import requests
import json
import traceback
from plexapi.server import PlexServer
import time
from fuzzywuzzy import fuzz, process
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import random
from googleapiclient.errors import HttpError
import datetime

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(text, color):
    color_code = getattr(Colors, color.upper(), '')
    print(f"{color_code}{text}{Colors.ENDC}")

def load_config():
    try:
        with open('config.yml', 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print_colored(f"Error loading config: {e}", 'red')
        exit(1)

def map_path(path, path_mappings):
    for remote, local in path_mappings.items():
        if path.startswith(remote):
            return path.replace(remote, local)
    return path

def get_plex_movies(config):
    try:
        plex = PlexServer(config['PLEX_URL'], config['PLEX_TOKEN'])
        movie_library = plex.library.section(config['MOVIE_LIBRARY_NAME'])
        return movie_library.all(), plex
    except Exception as e:
        print_colored(f"Error connecting to Plex: {e}", 'red')
        exit(1)

def get_gdrive_folder_id(folder_url):
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_url)
    if match:
        return match.group(1)
    return None

def backoff_time(attempt):
    base_delay = min(60, 2 ** attempt)  # Cap at 60 seconds
    jitter = random.uniform(0, 0.1 * base_delay)  # Add 0-10% jitter
    return base_delay + jitter

def get_gdrive_folders_api(folder_id, api_key):
    try:
        # Build the Drive service
        service = build('drive', 'v3', developerKey=api_key)
        
        # Get the list of files/folders in the parent folder with pagination
        movie_folders = []
        page_token = None
        total_folders = 0
        
        while True:
            try:
                # Make the request with page token if we have one
                results = service.files().list(
                    q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
                    fields="nextPageToken, files(id, name)",
                    pageSize=1000,
                    pageToken=page_token
                ).execute()
            except HttpError as error:
                if error.resp.status == 403:
                    # Rate limit hit - no retry
                    raise RateLimitException("Rate limit hit when listing folders")
                else:
                    raise  # Re-raise other errors
            
            items = results.get('files', [])
            total_folders += len(items)
            
            # Extract movie title and year from folder names
            movie_pattern = re.compile(r'(.*?)\s*\((\d{4})\)')
            
            for item in items:
                name = item['name']
                file_id = item['id']
                
                match = movie_pattern.search(name)
                if match:
                    title = match.group(1).strip()
                    year = match.group(2)
                    movie_folders.append((title, year, file_id))
                else:
                    # If no year in parentheses, just use the name as is
                    movie_folders.append((name, "", file_id))
            
            # Check if there are more pages
            page_token = results.get('nextPageToken')
            if not page_token:
                break
            
            # Add a small delay between pagination requests to avoid rate limiting
            time.sleep(1)
        
        if not movie_folders:
            print_colored("No folders found in Google Drive.", 'red')
            return []
        
        # Sort alphabetically
        movie_folders.sort(key=lambda x: x[0])
        
        print_colored(f"Found {total_folders} movie folders in Google Drive", 'green')
        
        # Save the list to a file
        with open("found_movie_folders.txt", "w", encoding="utf-8") as f:
            for title, year, _ in movie_folders:
                f.write(f"{title} ({year})\n")
        
        return movie_folders
    
    except RateLimitException:
        # Re-raise our custom exception
        raise
    except Exception as e:
        print_colored(f"Error accessing Google Drive API: {e}", 'red')
        print_colored(f"Traceback: {traceback.format_exc()}", 'red')
        return []

def find_theme_file_api(folder_id, api_key):
    try:
        # Build the Drive service
        service = build('drive', 'v3', developerKey=api_key)
        
        # Search for theme.mp3 in the folder
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and name='theme.mp3'",
                fields="files(id, name)",
                pageSize=10
            ).execute()
        except HttpError as error:
            if error.resp.status == 403:
                # Rate limit hit - no retry
                raise RateLimitException("Rate limit hit when searching for theme file")
            else:
                raise  # Re-raise other errors
        
        items = results.get('files', [])
        
        if not items:
            return None
        
        # Return the first matching file's ID
        return items[0]['id']
    
    except RateLimitException:
        # Re-raise our custom exception
        raise
    except Exception as e:
        print_colored(f"Error finding theme file: {e}", 'red')
        return None

def download_theme_api(file_id, output_path, api_key):
    try:
        # Build the Drive service
        service = build('drive', 'v3', developerKey=api_key)
        
        # Get the file
        try:
            request = service.files().get_media(fileId=file_id)
            
            # Download the file
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            # Check if file is empty (0kb)
            if os.path.getsize(output_path) == 0:
                print_colored("Downloaded file is empty (0kb). Removing it.", 'red')
                os.remove(output_path)
                return False
            
            return True
        except HttpError as error:
            if error.resp.status == 403:
                # Clean up any partial downloads
                if os.path.exists(output_path):
                    os.remove(output_path)
                # Rate limit hit - no retry
                raise RateLimitException("Rate limit hit when downloading file")
            else:
                # Clean up any partial downloads
                if os.path.exists(output_path):
                    os.remove(output_path)
                raise  # Re-raise other errors
    
    except RateLimitException:
        # Re-raise our custom exception
        raise
    except Exception as e:
        # Clean up any partial downloads
        if os.path.exists(output_path):
            os.remove(output_path)
        print_colored(f"Error downloading file: {e}", 'red')
        return False

def match_movie_titles(plex_movies, gdrive_folders):
    matches = {}
    
    for movie in plex_movies:
        title = movie.title
        year = str(movie.year) if movie.year else ""
        
        # First try exact match
        exact_match = False
        for gdrive_title, gdrive_year, folder_id in gdrive_folders:
            # For exact matches, require year to match if both have years
            if (title.lower() == gdrive_title.lower() or 
                title.lower().replace('&', 'and') == gdrive_title.lower().replace('&', 'and')):
                
                # If both have years, they must match
                if year and gdrive_year:
                    if year == gdrive_year:
                        matches[movie] = (gdrive_title, gdrive_year, folder_id)
                        print_colored(f"Exact match: Plex '{title} ({year})' -> GDrive '{gdrive_title} ({gdrive_year})'", 'green')
                        exact_match = True
                        break
                # If one doesn't have a year, still allow the match
                elif not year or not gdrive_year:
                    matches[movie] = (gdrive_title, gdrive_year, folder_id)
                    print_colored(f"Exact match (ignoring year): Plex '{title} ({year})' -> GDrive '{gdrive_title} ({gdrive_year})'", 'green')
                    exact_match = True
                    break
        
        if exact_match:
            continue
        
        # Try fuzzy matching if no exact match, but REQUIRE year to match
        best_match = None
        best_score = 0
        
        for gdrive_title, gdrive_year, folder_id in gdrive_folders:
            # Skip if years don't match and both have years
            if year and gdrive_year and year != gdrive_year:
                continue
                
            # Calculate similarity score
            score = fuzz.ratio(title.lower(), gdrive_title.lower())
            
            # Only consider matches above threshold
            if score > best_score and score > 80:  # Threshold of 80%
                best_score = score
                best_match = (gdrive_title, gdrive_year, folder_id)
        
        if best_match:
            matches[movie] = best_match
            print_colored(f"Fuzzy match ({best_score}%): Plex '{title} ({year})' -> GDrive '{best_match[0]} ({best_match[1]})'", 'green')
        else:
            print_colored(f"No match found for Plex movie: '{title} ({year})'", 'red')
    
    return matches

# Custom exception for rate limiting
class RateLimitException(Exception):
    pass

def save_state(movies_needing_themes, index):
    with open("theme_download_state.json", "w") as f:
        state = {
            "remaining_movies": [(movie.ratingKey, gdrive_title, gdrive_year, folder_id, theme_path) 
                               for movie, gdrive_title, gdrive_year, folder_id, theme_path in movies_needing_themes[index:]]
        }
        json.dump(state, f)
    print_colored("Saved current state for future resumption", "blue")

def load_state(plex):
    try:
        if os.path.exists("theme_download_state.json"):
            with open("theme_download_state.json", "r") as f:
                state = json.load(f)
                
            remaining_movies = []
            for rating_key, gdrive_title, gdrive_year, folder_id, theme_path in state["remaining_movies"]:
                try:
                    movie = plex.fetchItem(rating_key)
                    remaining_movies.append((movie, gdrive_title, gdrive_year, folder_id, theme_path))
                except Exception as e:
                    print_colored(f"Error fetching movie with rating key {rating_key}: {e}", "red")
            
            if remaining_movies:
                print_colored(f"Loaded state with {len(remaining_movies)} remaining movies", "green")
                return remaining_movies
    except Exception as e:
        print_colored(f"Error loading previous state: {e}", "red")
    
    return None

def schedule_next_run(config):
    cooldown_minutes = config.get('RETRY_COOLDOWN', 60)  # Default to 60 minutes if not specified
    next_run_time = datetime.datetime.now() + datetime.timedelta(minutes=cooldown_minutes)
    
    print_colored("\n========================================", 'blue')
    print_colored(f"SCHEDULING NEXT RUN AT: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}", 'blue')
    print_colored("========================================", 'blue')
    
    # Wait for the cooldown period
    print_colored(f"Waiting for {cooldown_minutes} minutes before retrying...", 'yellow')
    time.sleep(cooldown_minutes * 60)
    
    # Re-run the script
    print_colored("Cooldown period completed. Restarting script...", 'green')
    os.execv(sys.executable, ['python'] + sys.argv)

def main():
    print_colored("Movie Theme Downloader for Plex 1.0", 'header')
    
    # Load configuration
    config = load_config()
    path_mappings = config.get('PATH_MAPPINGS', {})
    
    # Check if API key is provided
    if 'GOOGLE_API_KEY' not in config:
        print_colored("Google API key is required in config.yml", 'red')
        print_colored("Please add GOOGLE_API_KEY: 'your-api-key' to your config.yml file", 'yellow')
        exit(1)
    
    # Check if RETRY_COOLDOWN is provided
    if 'RETRY_COOLDOWN' not in config:
        print_colored("RETRY_COOLDOWN not specified in config.yml, defaulting to 60 minutes", 'yellow')
    
    api_key = config['GOOGLE_API_KEY']
    
    # Track movies with downloaded themes
    movies_with_downloaded_themes = {}
    plex = None
    rate_limit_hit = False  # Add a flag to track rate limit hits
    
    try:
        # Get movies from Plex (needed for state loading)
        print_colored("Connecting to Plex...", 'blue')
        movies, plex = get_plex_movies(config)
        
        # Check if we have a saved state to resume from
        movies_needing_themes = load_state(plex)
        
        if not movies_needing_themes:
            # No saved state, start from scratch
            # Extract Google Drive folder ID
            folder_id = get_gdrive_folder_id(config['GDRIVE_URL'])
            if not folder_id:
                print_colored("Could not extract folder ID from URL", 'red')
                exit(1)
            
            # Get folders from Google Drive using API
            print_colored("Fetching movie folders from Google Drive using API...", 'blue')
            gdrive_folders = get_gdrive_folders_api(folder_id, api_key)
            
            if not gdrive_folders:
                print_colored("No movie folders found in Google Drive", 'red')
                exit(1)
            
            print_colored(f"Found {len(movies)} movies in Plex library", 'green')
            
            # Match Plex movies with Google Drive folders
            print_colored("Matching Plex movies with Google Drive folders...", 'blue')
            matches = match_movie_titles(movies, gdrive_folders)
            print_colored(f"Found {len(matches)} matching movies", 'green')
            
            # Pre-filter movies that already have themes
            print_colored("Checking for existing theme files...", 'blue')
            movies_needing_themes = []
            
            for movie, (gdrive_title, gdrive_year, folder_id) in matches.items():
                title = movie.title
                year = str(movie.year) if movie.year else ""
                local_path = map_path(movie.locations[0], path_mappings)
                theme_path = os.path.join(os.path.dirname(local_path), "theme.mp3")
                
                if os.path.exists(theme_path):
                    # Check if file is empty (0kb)
                    if os.path.getsize(theme_path) == 0:
                        print_colored(f"Empty theme file found for '{title} ({year})'. Removing it.", 'yellow')
                        os.remove(theme_path)
                        movies_needing_themes.append((movie, gdrive_title, gdrive_year, folder_id, theme_path))
                    else:
                        print_colored(f"Theme already exists for '{title} ({year})'", 'yellow')
                else:
                    movies_needing_themes.append((movie, gdrive_title, gdrive_year, folder_id, theme_path))
            
            print_colored(f"Found {len(movies_needing_themes)} matching movies that need themes", 'green')
        else:
            print_colored("Resuming from previous state", 'blue')
        
        # Process movies in smaller batches to avoid rate limiting
        batch_size = 5  # Process 5 movies at a time
        total_batches = (len(movies_needing_themes) + batch_size - 1) // batch_size
        
        for batch_idx, batch_start in enumerate(range(0, len(movies_needing_themes), batch_size)):
            batch_end = min(batch_start + batch_size, len(movies_needing_themes))
            current_batch = movies_needing_themes[batch_start:batch_end]
            current_batch_num = batch_idx + 1
            
            print_colored(f"\nProcessing batch {current_batch_num}/{total_batches}", 'blue')
            
            # Process each movie in the current batch
            for idx, (movie, gdrive_title, gdrive_year, folder_id, theme_path) in enumerate(current_batch):
                # Get movie details
                title = movie.title
                year = str(movie.year) if movie.year else ""
                
                print_colored(f"Processing movie {idx+1}/{len(current_batch)}: '{title} ({year})'", 'yellow')
                
                try:
                    # Find theme.mp3 in the folder
                    theme_id = find_theme_file_api(folder_id, api_key)
                    
                    if theme_id:
                        # Download the theme file
                        if download_theme_api(theme_id, theme_path, api_key):
                            print_colored(f"Successfully downloaded theme for '{title} ({year})'", 'green')
                            movies_with_downloaded_themes[(title, year)] = movie.ratingKey
                        else:
                            print_colored(f"Failed to download theme for '{title} ({year})'", 'red')
                    else:
                        print_colored(f"No theme.mp3 found for '{title} ({year})'", 'red')
                
                except RateLimitException:
                    # We hit a rate limit - save state and raise to exit
                    rate_limit_hit = True
                    save_state(movies_needing_themes, batch_start + idx)
                    raise
            
            # Add a delay between batches to avoid rate limiting
            if batch_end < len(movies_needing_themes):
                delay = random.uniform(10, 20)  # Random delay between 10-20 seconds
                print_colored(f"Pausing for {delay:.2f} seconds before next batch...", 'yellow')
                time.sleep(delay)
        
        # If we made it through all movies, clean up state file
        if os.path.exists("theme_download_state.json"):
            os.remove("theme_download_state.json")
            print_colored("All movies processed. Removed state file.", 'green')
        
    except RateLimitException:
        rate_limit_hit = True
        print_colored("\n========================================", 'red')
        print_colored("RATE LIMIT HIT - STOPPING EXECUTION", 'red')
        print_colored("========================================", 'red')
        print_colored(f"Successfully downloaded {len(movies_with_downloaded_themes)} themes before hitting rate limit.", 'yellow')
    
    except Exception as e:
        print_colored(f"Error: {e}", 'red')
        print_colored(f"Traceback: {traceback.format_exc()}", 'red')
    
    finally:
        # Refresh metadata for movies with new themes regardless of how we exited
        if movies_with_downloaded_themes and plex:
            print_colored("\nRefreshing metadata for movies with new themes:", 'blue')
            for (title, year), rating_key in movies_with_downloaded_themes.items():
                if rating_key:
                    try:
                        item = plex.fetchItem(rating_key)
                        print_colored(f"Refreshing metadata for '{item.title}'", 'yellow')
                        item.refresh()
                        time.sleep(1)
                    except Exception as e:
                        print_colored(f"Failed to refresh metadata for '{title} ({year})': {e}", 'red')
            
            print_colored(f"\nMetadata refresh complete for {len(movies_with_downloaded_themes)} movies.", 'green')
        
        # This ensures we don't schedule when all processing is complete
        if rate_limit_hit and os.path.exists("theme_download_state.json") and config.get('RETRY_COOLDOWN'):
            schedule_next_run(config)
        elif rate_limit_hit:
            print_colored("Please wait a while before running the script again.", 'yellow')
            print_colored("Google Drive API limits the number of requests you can make in a given time period.", 'yellow')
            print_colored("Try running the script again in 1-2 hours.", 'yellow')
        
        print_colored(f"\nScript execution complete. Added themes for {len(movies_with_downloaded_themes)} movies.", 'header')

if __name__ == "__main__":
    main()