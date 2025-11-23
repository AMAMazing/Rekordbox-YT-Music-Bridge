# DJ Playlist Sync

A desktop application designed for DJs and audiophiles to bridge the gap between cloud-based playlists and local music libraries. This tool streamlines the process of organizing metadata, segregating artists, and caching content for offline archival use.

Built with PyQt6 and styled with a professional dark theme optimized for low-light environments.

## Features

- **Library Synchronization**: Import public or private playlist metadata via URL.
- **Secure Integration**: Log in securely to access and sync your personal cloud library and unlisted collections.
- **Auto-Discovery**: Automatically detects and lists your saved online playlists for one-click syncing.
- **Advanced Micro-Playlists**:
    - **Artist Segregation**: Automatically organize large playlists into custom "micro-playlists" based on specific artists.
    - **Smart Sorting**: Keeps your main track view clean by clustering artist discographies into folder structures.
    - **Multi-Tagging**: Tracks with multiple artists appear correctly in all relevant micro-playlists without file duplication.
- **Intelligent Track View**: A hierarchical view displaying micro-playlists as folders alongside loose tracks for intuitive navigation.
- **Customizable Naming & Sorting**: Define how your local files are organized:
    - `TrackName - ArtistName`
    - `ArtistName - TrackName`
    - `001 - TrackName - ArtistName` (Preserve playlist order)
- **Background Caching**: File processing runs in a separate thread, keeping the UI responsive during large batch operations.
- **Progress Monitoring**: Real-time status bars and time estimates for batch processing.
- **Update Detection**: Automatically checks synced playlists for new additions and flags them for update.

## Requirements

All required Python packages are listed in the `requirements.txt` file.

## Setup

### 1. Install Dependencies
Open your terminal or command prompt in the project directory and run:
```bash
pip install -r requirements.txt
```

2. API Credentials
This application requires personal API credentials to query playlist metadata.
 * Go to the Google Cloud Console.
 * Create a new project.
 * Enable the "YouTube Data API v3".
 * Navigate to "Credentials", click "Create Credentials", and select "OAuth client ID".
 * Select "Desktop app" as the application type.
 * Download the JSON credentials file.
 * Rename the file to client_secrets.json and place it in the project root directory.
3. Run the Application
python main.py

Usage
 * Authenticate: Click the "Login" button to authorize the application to read your library metadata.
 * Sync Metadata:
   * Your online playlists will appear in the "Cloud Library" panel.
   * Double-click any playlist to sync its metadata to the local database.
   * Use "Add by URL" for external public playlists.
 * Organize (Micro-Playlists):
   * Select a synced playlist.
   * Click "Create Micro-Playlist" to filter specific artists into their own sub-folder.
 * Offline Cache:
   * Select tracks or entire folders in the view.
   * Click "Cache Selected" to archive the files locally to your configured directory.


### ⚠️ Disclaimer
For Educational and Archival Use Only.
This project is a personal library management tool intended to help users organize media they have already acquired or have the legal right to access.
 * The developer does not support or condone copyright infringement.
 * Users are solely responsible for ensuring their use of this tool complies with all local laws and the Terms of Service of any third-party platforms.
 * This project is not affiliated with, endorsed by, or in any way officially connected with Google LLC, YouTube, or AlphaTheta Corporation (Pioneer DJ/Rekordbox).
