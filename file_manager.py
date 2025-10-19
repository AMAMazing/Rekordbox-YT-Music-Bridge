import re
import os

class FileManager:
    """
    Handles the creation and management of file and directory names for downloaded tracks.
    This class provides a centralized system for defining filename formats, ensuring that
    both the downloader and the download detector use the exact same naming conventions.
    """

    def __init__(self, config):
        """
        Initializes the FileManager with a given configuration.
        The configuration dictionary determines the file naming rules.

        Args:
            config (dict): A dictionary containing filename formatting options.
                           Expected keys: 'numbering', 'numbering_style', 'name_order'.
        """
        self.config = config

    def sanitize(self, name):
        """
        Removes characters from a string that are not allowed in file or directory names.

        Args:
            name (str): The input string to be sanitized.

        Returns:
            str: The sanitized string, safe to be used as a part of a filename.
        """
        return re.sub(r'[\\/*?:"<>|]', '_', name)

    def get_base_filename(self, track_info):
        """
        Constructs the base filename (artist and track name) without any numeric prefix.
        This is used for comparison by the TrackChecker.

        Args:
            track_info (dict): A dictionary containing the track's metadata.

        Returns:
            str: The generated base filename.
        """
        title = self.sanitize(track_info.get('title', 'Unknown Title'))
        artists = self.sanitize(', '.join([artist['name'] for artist in track_info.get('artists', [])]))
        
        name_parts = []
        if self.config.get('name_order') == 'artist_track':
            name_parts.extend([artists, title])
        else:  # Default to 'track_artist'
            name_parts.extend([title, artists])

        return '_'.join(filter(None, name_parts))

    def get_filename(self, track_info, playlist_position=None, total_tracks=None):
        """
        Constructs a full filename for a track, including a numeric prefix if configured.

        Args:
            track_info (dict): A dictionary containing the track's metadata.
            playlist_position (int, optional): The 1-based index of the track in its playlist.
            total_tracks (int, optional): The total number of tracks in the playlist.

        Returns:
            str: The generated full filename for the track.
        """
        filename_base = self.get_base_filename(track_info)
        number_prefix = self._get_number_prefix(track_info, playlist_position, total_tracks)
        
        if number_prefix:
            return f"{number_prefix}_{filename_base}"
        return filename_base

    def _get_number_prefix(self, track_info, playlist_position, total_tracks):
        """
        Generates the numeric prefix for a filename based on the configuration.
        """
        numbering_type = self.config.get('numbering')
        if not numbering_type or numbering_type == 'none':
            return ""

        number = 0
        if numbering_type == 'playlist_order' and playlist_position is not None:
            number = playlist_position
        elif numbering_type == 'release_year' and track_info.get('year'):
            return str(track_info.get('year'))

        if number and total_tracks:
            num_digits = len(str(total_tracks))
            return str(number).zfill(num_digits)
        
        return ""

    def get_track_directory(self, download_dir, playlist_name, microplaylist_name=None):
        """
        Constructs the full directory path where a track should be saved.
        """
        sanitized_playlist = self.sanitize(playlist_name)
        path_parts = [download_dir, sanitized_playlist]
        
        if microplaylist_name:
            sanitized_micro = self.sanitize(microplaylist_name)
            path_parts.append(sanitized_micro)
            
        return os.path.join(*path_parts)
