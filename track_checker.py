import os
import re

class TrackChecker:
    """
    Detects whether a track has already been downloaded using flexible matching.
    This class uses the FileManager to generate an expected base filename (without numbers)
    and then searches for a matching file in the target directory, ignoring any numeric prefixes.
    """

    def __init__(self, file_manager, download_directory):
        """
        Initializes the TrackChecker.

        Args:
            file_manager (FileManager): An instance of the FileManager to handle naming and paths.
            download_directory (str): The root directory where tracks are saved.
        """
        self.file_manager = file_manager
        self.download_directory = download_directory
        self.local_files_map = self._scan_directory()

    def _scan_directory(self):
        """
        Scans the download directory recursively and builds a map of directories to their files.

        Returns:
            dict: A dictionary where keys are directory paths and values are lists of filenames.
        """
        dir_map = {}
        if not os.path.exists(self.download_directory):
            return dir_map

        for root, _, files in os.walk(self.download_directory):
            mp3_files = [f for f in files if f.endswith(".mp3")]
            if mp3_files:
                dir_map[root] = mp3_files
        return dir_map

    def rescan(self):
        """
        Forces a re-scan of the download directory to update the list of local files.
        """
        self.local_files_map = self._scan_directory()

    def is_downloaded(self, track_info, playlist_info, microplaylist_name=None):
        """
        Checks if a specific track is downloaded using flexible, prefix-agnostic matching.
        It generates the expected filename without a number and looks for a file in the
        target directory that matches this base name, regardless of any numeric prefix.

        Args:
            track_info (dict): Metadata of the track to check.
            playlist_info (dict): Metadata of the parent playlist.
            microplaylist_name (str, optional): The name of the micro-playlist, if applicable.

        Returns:
            str or None: The full file path if a match is found, otherwise None.
        """
        playlist_name = playlist_info.get('title', 'Unknown Playlist')
        
        # 1. Get the expected directory and base filename (without number prefix)
        target_directory = self.file_manager.get_track_directory(self.download_directory, playlist_name, microplaylist_name)
        expected_base_name = self.file_manager.get_base_filename(track_info)

        # 2. Get the list of files in the target directory from our scanned map
        files_in_dir = self.local_files_map.get(target_directory)
        if not files_in_dir:
            return None

        # 3. Iterate through the files and check for a match
        for filename_with_ext in files_in_dir:
            # Remove the .mp3 extension
            filename_no_ext = os.path.splitext(filename_with_ext)[0]
            
            # Strip the numeric prefix, if it exists
            parts = filename_no_ext.split('_', 1)
            
            # If there's a numeric prefix, the part to compare is the second part.
            # Otherwise, it's the whole filename.
            if len(parts) > 1 and parts[0].isdigit():
                base_to_compare = parts[1]
            else:
                base_to_compare = filename_no_ext
            
            # 4. Compare the stripped local filename with the expected base name
            if base_to_compare == expected_base_name:
                return os.path.join(target_directory, filename_with_ext)
                
        return None
