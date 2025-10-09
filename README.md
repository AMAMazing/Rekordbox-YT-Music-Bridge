# Rekordbox YT Music Bridge

A desktop application designed for DJs and music enthusiasts who use Rekordbox and source their music from YouTube or YouTube Music. This tool bridges the gap between your online playlists and your local music library, providing a seamless way to download and organize your tracks.

The application is built with PyQt6 and styled with a dark, Rekordbox-inspired theme.

## Features

- **Playlist Syncing**: Add public or private YouTube/YT Music playlists by URL.
- **Google Account Integration**: Log in securely with your Google account to access and sync your private and unlisted YouTube playlists.
- **Automatic Playlist Discovery**: After logging in, the application automatically discovers all playlists on your YouTube account, allowing you to sync them with a single double-click.
- **Advanced Micro-Playlists**:
    - For each synced playlist, create custom micro-playlists based on one or more artists.
    - Give your micro-playlists a custom name or let it default to the artist names.
    - Songs belonging to a micro-playlist are automatically segregated, keeping your main playlist view clean.
    - A single track with multiple artists will correctly appear in all relevant micro-playlists across different parent playlists.
- **Intelligent Track View**: The track panel displays your micro-playlists as folders at the top, followed by all remaining tracks, for clear and intuitive organization.
- **Smart File Naming & Sorting**: Choose how your downloaded files are named:
    - `TrackName_ArtistName`
    - `ArtistName_TrackName`
    - Numbered by upload date (`001_TrackName_ArtistName`)
- **Background Downloading**: The downloader runs in a separate thread, so the application remains responsive even during large downloads.
- **Progress & Estimates**: Real-time progress bars and status updates show the status of each track, along with estimates for total size and time remaining.
- **Automatic Sync Check**: On startup, the application checks all your synced playlists for new songs and notifies you of any updates.
- **Rekordbox-Inspired UI**: A sleek, dark theme that feels right at home for DJs.

## Requirements

All required Python packages are listed in the `requirements.txt` file.

## Setup

### 1. Install Dependencies:
Open your terminal or command prompt in the project directory and run:
```
pip install -r requirements.txt
```

### 2. Google API Credentials (Crucial Step):
This application uses the YouTube Data API v3 to access private playlist information. To enable this, you must obtain your own API credentials from the Google Cloud Console.

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project.
3.  Enable the **"YouTube Data API v3"**.
4.  Go to "Credentials", click "Create Credentials", and choose "OAuth client ID".
5.  Select **"Desktop app"** as the application type.
6.  Once created, download the JSON file.
7.  **Rename the downloaded file to `client_secrets.json`** and place it in the root directory of this project (the same folder as `main.py`).

**Note**: The application will not be able to access private playlists without this file.

### 3. Run the Application:
Once the dependencies are installed and `client_secrets.json` is in place, you can run the application:
```
python main.py
```

## Usage

- **Login**: Click the "Login with Google" button. Your web browser will open, prompting you to authorize the application. After you approve, the application will be authenticated. The button will change to "Logout".
- **Sync Playlists**:
    - After logging in, your YouTube playlists will appear in the left panel under "My YouTube Playlists".
    - Double-click any playlist to "sync" it. It will move to the "Synced Playlists" section and be saved for future sessions.
    - Alternatively, use the "Add by URL" button to add any public playlist.
- **Create Micro-Playlists**:
    - Select a playlist under "Synced Playlists".
    - Click the "Create Micro-Playlist" button.
    - In the dialog, select one or more artists (use the search bar to filter) and optionally provide a custom name.
    - Click "Create". The track view on the right will update to show the new micro-playlist as a folder.
- **Download Tracks**:
    - In the right-hand track view, select individual tracks or entire micro-playlist folders.
    - Choose your preferred file naming convention from the "Sort by" dropdown.
    - Click "Download Selected" and choose a destination folder.

