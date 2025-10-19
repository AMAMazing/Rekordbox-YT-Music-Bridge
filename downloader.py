import os
import time
import re
import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Downloader(QThread):
    progress_update = pyqtSignal(str, str, str)
    download_finished = pyqtSignal(str, bool, str)  # videoId, success, message
    estimation_update = pyqtSignal(str)
    overall_progress = pyqtSignal(int)
    all_downloads_finished = pyqtSignal()

    def __init__(self, tracks_to_download, output_paths, sort_option, max_workers=3):
        super().__init__()
        self.tracks_with_paths = list(zip(tracks_to_download, output_paths))
        self.sort_option = sort_option
        self.max_workers = max_workers
        self.is_running = True
        self.total_tracks = len(tracks_to_download)
        self.completed_tracks = 0
        self.cumulative_time = 0
        self.lock = threading.Lock()

    def progress_hook(self, d):
        video_id = d.get('info_dict', {}).get('id')
        if not video_id:
            return

        if d['status'] == 'downloading':
            percentage = d.get('_percent_str', '0.0%')
            speed = d.get('_speed_str', 'N/A')
            self.progress_update.emit(video_id, f"Downloading ({speed})", percentage)
        elif d['status'] == 'finished':
            self.progress_update.emit(video_id, "Converting...", "100%")

    def _download_track(self, track_with_path, index):
        if not self.is_running:
            return

        track, output_path = track_with_path
        start_time = time.time()
        
        video_id = track['videoId']
        track_title = track.get('title', 'N/A')
        
        artists_list = []
        for artist in track.get('artists', []):
            if 'name' in artist:
                cleaned_name = artist['name'].replace(' - Topic', '').strip()
                if cleaned_name:
                    artists_list.append(cleaned_name)
        artists = ', '.join(artists_list)

        if self.sort_option == "Track Name":
            filename_template = f"{track_title}_{artists}"
        elif self.sort_option == "Artist Name":
            filename_template = f"{artists}_{track_title}"
        elif self.sort_option == "Upload Date":
            num_digits = len(str(self.total_tracks))
            filename_template = f"{str(index + 1).zfill(num_digits)}_{track_title}_{artists}"
        else: # Date Added is the default
            num_digits = len(str(self.total_tracks))
            filename_template = f"{str(index + 1).zfill(num_digits)}_{track_title}_{artists}"
        
        safe_filename = re.sub(r'[\/*?:"<>|]', '_', filename_template)
        output_template = os.path.join(output_path, safe_filename + '.%(ext)s')

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
            'source_address': '0.0.0.0',
            'postprocessor_args': [
                '-metadata', f'artist={artists}',
                '-metadata', f'title={track_title}'
            ]
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
            
            final_filepath = os.path.join(output_path, safe_filename + '.mp3')
            
            if os.path.exists(final_filepath) and os.path.getsize(final_filepath) > 0:
                self.download_finished.emit(video_id, True, "Download successful")
            else:
                self.download_finished.emit(video_id, False, "File is empty or missing.")
                logging.error(f"Post-download check failed for {track_title}: File is empty or missing at {final_filepath}")

        except yt_dlp.utils.DownloadError as e:
            self.download_finished.emit(video_id, False, f"Download Error: {str(e)}")
            logging.error(f"Download Error for {track_title} ({video_id}): {e}")
        except Exception as e:
            self.download_finished.emit(video_id, False, f"Unexpected Error: {str(e)}")
            logging.error(f"Unexpected Error for {track_title} ({video_id}): {e}")
        
        end_time = time.time()
        
        with self.lock:
            self.completed_tracks += 1
            if self.completed_tracks > 0:
                self.cumulative_time += (end_time - start_time)
                
                progress_percent = int((self.completed_tracks / self.total_tracks) * 100)
                self.overall_progress.emit(progress_percent)
                
                avg_time_per_track = self.cumulative_time / self.completed_tracks
                remaining_tracks = self.total_tracks - self.completed_tracks
                time_remaining_sec = avg_time_per_track * remaining_tracks
                
                if time_remaining_sec > 0:
                    mins, secs = divmod(time_remaining_sec, 60)
                    time_remaining_str = f"{int(mins)}m {int(secs)}s remaining"
                    self.estimation_update.emit(time_remaining_str)
                else:
                    self.estimation_update.emit("Finishing up...")

    def run(self):
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._download_track, track_with_path, i): track_with_path for i, track_with_path in enumerate(self.tracks_with_paths)}

            for future in as_completed(futures):
                if not self.is_running:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error processing a download future: {e}")

        
        if self.is_running:
            self.all_downloads_finished.emit()

    def stop(self):
        self.is_running = False
