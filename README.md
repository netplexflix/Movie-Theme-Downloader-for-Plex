//As per October 2026, Themerr has been revived, which makes this script redundant. [Check Themerr out here.](https://github.com/LizardByte/Themerr)

# 🎵 Movie Theme Downloader for Plex (TDFP) 🎬

This script automatically matches your Plex movies with movie themes from [/r/PlexThemes'](https://www.reddit.com/r/PlexThemes/) /u/chainwood's Google Drive and downloads them to the correct locations.

Requires [a Google Drive API Key](https://support.google.com/googleapi/answer/6158862)


## ✨ Features

- 🎵 Automatic Theme Discovery: Finds theme music for your Plex movies from Google Drive
- 🔍 Smart Matching Algorithm: Uses both exact and fuzzy matching to find the right themes
- 🧠 Intelligent Resume: Saves progress when rate limits are hit and automatically resumes
- ⏱️ Automatic Retry: Waits for cooldown period and continues downloading when rate limits are encountered
- 🎨 Path Mapping Support: Maps paths between different systems (e.g. Docker to host paths)
- 🔄 Metadata Refresh: Automatically refreshes Plex metadata after downloading themes
- 🚦 Rate Limit Handling: Smart handling of Google Drive API rate limits

---

## 🍿 Plex Settings
Before downloading Movie themes, make sure your [Plex settings](https://support.plex.tv/articles/200220717-local-media-assets-tv-shows/) are correct. </br>
If using the new Plex TV Series agent you only need to enable “Use local Assets” in the libraries settings.
For each client, you need to enable "Play Theme Music"

>[!Note]
> Gdrive has pretty low rate limits. You'll only be able to download about 30 themes at once.
> Therefor I suggest you simply go to [the Gdrive folder](https://drive.google.com/drive/folders/128O8hwhxmPppwJ3ssGKQoepMrKLB5tNA), manually download all themes and paste them into your Movie directory.
> You can then schedule the script to search for new additions. If you choose to let the script handle all themes, keep in mind this may take a long time due to the rate limit timeouts.

---

## 🛠️ Installation
1️⃣ Clone the repo:

```sh
git clone https://github.com/netplexflix/Movie-Theme-Downloader-for-Plex/.git
cd Movie-Theme-Downloader-for-Plex
```

>[!TIP]
>If you don't know what that means, then simply download the script by pressing the green 'Code' button above and then 'Download Zip'.
>Extract the files to your desired folder.
  

2️⃣ Install Dependencies

Ensure you have Python installed (>=3.11). <br/>

Open a Terminal in the script's directory
>[!TIP]
>Windows Users: <br/>
>Go to the TDFP folder (where TDFP.py is). Right mouse click on an empty space in the folder and click Open in Windows Terminal

Install the required dependencies by pasting the following code:
```sh
pip install -r requirements.txt
```

---
## ⚙️ Configuration

Rename config.example.yml to config.yml and edit the needed settings:

- PLEX_URL: Adjust if needed
- PLEX_TOKEN: [Finding your Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- MOVIE_LIBRARY_NAME: Rename if needed.
- GDRIVE_URL: Leave as is, unless you have another Gdrive to connect to.
- GOOGLE_API_KEY: [More info here](https://support.google.com/googleapi/answer/6158862)
- RETRY_COOLDOWN: increase if needed
- PATH_MAPPINGS: edit if needed

---

## 🚀 Usage - Running the Script

Open a Terminal in your script directory and launch the script with:
```sh
python TDFP.py
```


The script will:
- Connect to your Plex server and fetch all movies
- Scan the Google Drive folder for movie themes
- Check which movies have matching themes on the Gdrive that haven't been downloaded yet
- Download themes to the correct locations
- Refresh Plex metadata for the updated movies (this is necessary for Plex to detect the Themes.



If the script hits Google Drive API rate limits, it will:
- Save its current state
- Wait for the cooldown period specified in the config
- Automatically resume where it left off

>[!TIP]
>Windows users can create a batch file to quickly launch the script.<br/>
>Type "[path to your python.exe]" "[path to the script]" into a text editor
>
>For example:
>```
>"C:\Users\User1\AppData\Local\Programs\Python\Python311\python.exe" "P:\TDFP\TDFP.py"
>pause
>```
>Save as a .bat file. You can now double click this batch file to directly launch the script.

---
## 🕵️ Check.py
Sometimes Plex fails to pick up a local file (in this case theme.mp3) even after refreshing the metadata.
I have included a script (check.py) that checks your Plex and local folders to find any themes that exist but weren't picked up by Plex.
You can run `python check.py` to check if all themes are correctly picked up by Plex.

---

## ⚠️ Need Help or Have Feedback?
Join our [Discord](https://discord.gg/VBNUJd7tx3)

---

## ❓ FAQ

Q: Why do I need a Google API key?  
A: The script uses the Google Drive API to access and download theme files. The API key allows authenticated access to Google's services.


Q: How does the script match movies?  
A: The script first tries to find exact matches between your Plex movie titles and the Google Drive folders. If that fails, it uses fuzzy matching with a 70% similarity threshold, while ensuring years match if available.


Q: What happens if Google Drive rate limits me?  
A: The script will save its current state, wait for the cooldown period specified in your config (RETRY_COOLDOWN), and then automatically resume where it left off.



---  

## ❤️ Support the Project

If you find this project useful, please ⭐ star the repository and share it!

<br/>

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/neekokeen)
