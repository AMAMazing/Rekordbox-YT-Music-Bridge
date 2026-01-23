# DJ Library Sync Bridge

A desktop application designed for DJs and audiophiles to bridge the gap between cloud-based playlists and local music libraries. This tool streamlines the process of organizing metadata, segregating artists, and caching content for offline archival use.

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

## Easy Setup (Windows Application)

For users who do not want to install Python, simply run the standalone executable.

### 1. Requirements
Although the application handles the code, you need two external items for it to function:
1.  **API Credentials (`client_secrets.json`)**: Required to talk to YouTube.
2.  **FFmpeg**: Required to convert audio to high-quality MP3.

### 2. Installation Steps

1.  **Download the App**: Get `DJ Library Sync Bridge.exe` from the Releases page (or `dist` folder).
2.  **Get FFmpeg**:
    -   Download `ffmpeg-release-essentials.zip` from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
    -   Extract `ffmpeg.exe` and `ffprobe.exe` (found in the `bin` folder) and place them **in the same folder** as the application.
3.  **Get API Credentials**:
    -   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    -   Create a project and enable "YouTube Data API v3".
    -   Create "OAuth client ID" credentials (select "Desktop app").
    -   Download the JSON file, rename it to `client_secrets.json`, and place it **in the same folder** as the application.
4.  **Run**: Double-click `DJ Library Sync Bridge.exe`.

---

## Developer Setup (Python Source)

If you want to modify the code or run from source:

### Requirements
All required Python packages are listed in `requirements.txt`.

### 1. Install Dependencies
Open your terminal in the project directory:
```bash
pip install -r requirements.txt
```

### 2. API Credentials
Follow step 3 in the "Easy Setup" guide above to generate `client_secrets.json`. Place it in the project root.

### 3. Run the Application
```bash
python main.py
```

## Usage Guide
 * **Authenticate**: Click "Login with Cloud" to authorize library access.
 * **Sync Metadata**:
   * Your online playlists will appear in the "Cloud Playlists" section.
   * Double-click any playlist to sync its metadata.
   * Use "Add by URL" for external public playlists.
 * **Organize (Micro-Playlists)**:
   * Select a synced playlist.
   * Click "Create Micro" to filter specific artists into their own sub-folder.
 * **Offline Cache**:
   * Select tracks or folders.
   * Click "Cache Selected" to download MP3s to your configured directory.

## ⚠️ Disclaimer
**For Educational and Archival Use Only.**
This project is a personal library management tool intended to help users organize media they have already acquired or have the legal right to access.
 * The developer does not support or condone copyright infringement.
 * Users are solely responsible for ensuring their use of this tool complies with all local laws and the Terms of Service of any third-party platforms.
 * This project is not affiliated with Google LLC, YouTube, or AlphaTheta Corporation.

