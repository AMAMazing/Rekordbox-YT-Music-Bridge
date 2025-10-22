import os
import time
import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DownloadHandler(QThread):
    """
    Manages the downloading of tracks from YouTube.
    This class handles the entire download process, including progress reporting,
    error handling, and file naming, using the FileManager for consistency.
    """
    progress_update = pyqtSignal(str, str, str)
    download_finished = pyqtSignal(str, bool, str)
    estimation_update = pyqtSignal(str)
    overall_progress = pyqtSignal(int)
    all_downloads_finished = pyqtSignal()

    def __init__(self, tracks_to_download, file_manager, download_directory, max_workers=3, cookies_file=None):
        """
        Initializes the DownloadHandler.

        Args:
            tracks_to_download (list): A list of track metadata dictionaries to be downloaded.
            file_manager (FileManager): An instance of the FileManager to handle naming and paths.
            download_directory (str): The root directory where tracks will be saved.
            max_workers (int): The number of concurrent download threads to use.
            cookies_file (str): Path to Netscape format cookies file (optional but recommended).
        """
        super().__init__()
        self.tracks_to_download = tracks_to_download
        self.file_manager = file_manager
        self.download_directory = download_directory
        self.max_workers = max_workers
        self.cookies_file = cookies_file
        self.is_running = True
        self.total_tracks = len(tracks_to_download)
        self.completed_tracks = 0
        self.cumulative_time = 0
        self.lock = threading.Lock()

    def progress_hook(self, d):
        """
        A hook for yt-dlp to report download progress.
        """
        video_id = d.get('info_dict', {}).get('id')
        if not video_id:
            return

        if d['status'] == 'downloading':
            percentage = d.get('_percent_str', '0.0%')
            speed = d.get('_speed_str', 'N/A')
            self.progress_update.emit(video_id, f"Downloading ({speed})", percentage)
        elif d['status'] == 'finished':
            self.progress_update.emit(video_id, "Converting...", "100%")

    def _download_track(self, track_info, playlist_position):
        """
        Downloads a single track.
        """
        if not self.is_running:
            return

        video_id = track_info['videoId']
        start_time = time.time()

        # Generate paths and filenames using FileManager
        playlist_name = track_info.get('playlist_title', 'Unknown Playlist')
        microplaylist_name = track_info.get('microplaylist_title')
        total_tracks_in_playlist = track_info.get('playlist_track_count', self.total_tracks)
        output_path = self.file_manager.get_track_directory(self.download_directory, playlist_name, microplaylist_name)
        
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
            
        filename = self.file_manager.get_filename(track_info, playlist_position, total_tracks_in_playlist)
        output_template = os.path.join(output_path, filename + '.%(ext)s')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }, {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }],
            'progress_hooks': [self.progress_hook],
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'quiet': True,
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            # Enhanced anti-bot measures
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                }
            },
            # User agent and headers
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            'postprocessor_args': [
                '-metadata', f"artist={', '.join([a['name'] for a in track_info.get('artists', [])])}",
                '-metadata', f"title={track_info.get('title', 'N/A')}"
            ]
        }

        # Add cookies if provided
        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
            logging.info(f"Using cookies file: {self.cookies_file}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
            
            final_filepath = os.path.join(output_path, filename + '.mp3')
            if os.path.exists(final_filepath) and os.path.getsize(final_filepath) > 0:
                self.download_finished.emit(video_id, True, "Download successful")
            else:
                self.download_finished.emit(video_id, False, "File is empty or missing.")

        except Exception as e:
            self.download_finished.emit(video_id, False, f"Error: {str(e)}")
            logging.error(f"Error downloading {video_id}: {e}")
        
        end_time = time.time()
        
        with self.lock:
            self.completed_tracks += 1
            self.cumulative_time += (end_time - start_time)
            
            progress_percent = int((self.completed_tracks / self.total_tracks) * 100)
            self.overall_progress.emit(progress_percent)
            
            avg_time = self.cumulative_time / self.completed_tracks
            remaining = self.total_tracks - self.completed_tracks
            time_left = avg_time * remaining
            
            if time_left > 0:
                mins, secs = divmod(time_left, 60)
                self.estimation_update.emit(f"{int(mins)}m {int(secs)}s remaining")
            else:
                self.estimation_update.emit("Finishing...")

    def run(self):
        """
        Starts the download process using a thread pool.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._download_track, track, i + 1): track for i, track in enumerate(self.tracks_to_download)}

            for future in as_completed(futures):
                if not self.is_running:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"A download future resulted in an error: {e}")
        
        if self.is_running:
            self.all_downloads_finished.emit()

    def stop(self):
        """
        Stops the download process.
        """
        self.is_running = False