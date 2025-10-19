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

    def segregate_tracks(self, all_synced_playlists):
        micro_playlist_tracks = defaultdict(list)
        remaining_playlist_tracks = defaultdict(list)

        for p_id, p_data in all_synced_playlists.items():
            parent_mps = self.microplaylists.get(p_id, [])
            
            for track in p_data.get('tracks', []):
                assigned_to_any_micro = False
                track_artists_lower = {artist['name'].lower().replace(' - topic', '').strip() for artist in track.get('artists', []) if 'name' in artist}

                if isinstance(parent_mps, list):
                    for mp in parent_mps:
                        if isinstance(mp, dict) and 'artists' in mp and 'name' in mp:
                            mp_artists_lower = {artist.lower() for artist in mp['artists']}
                            if not track_artists_lower.isdisjoint(mp_artists_lower):
                                micro_playlist_tracks[(p_id, mp['name'])].append(track)
                                assigned_to_any_micro = True
                
                if not assigned_to_any_micro:
                    remaining_playlist_tracks[p_id].append(track)
            
        return micro_playlist_tracks, remaining_playlist_tracks
