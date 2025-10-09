import json
import os
from collections import defaultdict

class MicroPlaylistHandler:
    def __init__(self, config_path='microplaylists.json'):
        self.config_path = config_path
        self.microplaylists = self.load_microplaylists()

    def load_microplaylists(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {} # Handle corrupted file
        return {}

    def save_microplaylists(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.microplaylists, f, indent=4)

    def get_microplaylists_for_playlist(self, parent_playlist_id):
        return self.microplaylists.get(parent_playlist_id, [])

    def add_microplaylist(self, parent_playlist_id, name, artists):
        if parent_playlist_id not in self.microplaylists:
            self.microplaylists[parent_playlist_id] = []
        
        for mp in self.microplaylists[parent_playlist_id]:
            if isinstance(mp, dict) and mp.get('name') == name:
                return False
        
        self.microplaylists[parent_playlist_id].append({"name": name, "artists": artists})
        self.save_microplaylists()
        return True

    def remove_microplaylist(self, parent_playlist_id, name):
        if parent_playlist_id in self.microplaylists:
            self.microplaylists[parent_playlist_id] = [mp for mp in self.microplaylists[parent_playlist_id] if isinstance(mp, dict) and mp.get('name') != name]
            if not self.microplaylists[parent_playlist_id]:
                del self.microplaylists[parent_playlist_id]
            self.save_microplaylists()

    def update_microplaylist(self, parent_playlist_id, original_name, new_name, new_artists):
        if parent_playlist_id in self.microplaylists:
            # Check if new_name already exists (and it's not the same microplaylist)
            for mp in self.microplaylists[parent_playlist_id]:
                if isinstance(mp, dict) and mp.get('name') == new_name and mp.get('name') != original_name:
                    return False, f"A micro-playlist named '{new_name}' already exists."

            found = False
            for mp in self.microplaylists[parent_playlist_id]:
                if isinstance(mp, dict) and mp.get('name') == original_name:
                    mp['name'] = new_name
                    mp['artists'] = new_artists
                    found = True
                    break
            
            if found:
                self.save_microplaylists()
                return True, "Micro-playlist updated successfully."
            else:
                return False, "Original micro-playlist not found."
        return False, "Parent playlist not found."

    def get_all_activated_artists_globally(self):
        all_artists = set()
        for parent_mps in self.microplaylists.values():
            if isinstance(parent_mps, list):
                for mp in parent_mps:
                    # FIX: Add guard for old data format
                    if isinstance(mp, dict) and 'artists' in mp:
                        all_artists.update(artist.lower() for artist in mp['artists'])
        return all_artists

    def segregate_tracks(self, all_synced_playlists):
        all_activated_artists_global = self.get_all_activated_artists_globally()
        
        micro_playlist_tracks = defaultdict(list)
        remaining_playlist_tracks = defaultdict(list)

        for p_id, p_data in all_synced_playlists.items():
            for track in p_data.get('tracks', []):
                track_artists_lower = {artist['name'].lower().replace(' - topic', '').strip() for artist in track.get('artists', []) if 'name' in artist}
                
                is_in_any_micro = not track_artists_lower.isdisjoint(all_activated_artists_global)

                if is_in_any_micro:
                    for parent_id, mps in self.microplaylists.items():
                        if isinstance(mps, list):
                            for mp in mps:
                                # FIX: Add guard for old data format
                                if isinstance(mp, dict) and 'artists' in mp and 'name' in mp:
                                    mp_artists_lower = {artist.lower() for artist in mp['artists']}
                                    if not track_artists_lower.isdisjoint(mp_artists_lower):
                                        micro_playlist_tracks[(parent_id, mp['name'])].append(track)
                else:
                    remaining_playlist_tracks[p_id].append(track)
        
        return micro_playlist_tracks, remaining_playlist_tracks
