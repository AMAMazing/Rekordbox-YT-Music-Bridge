import sys
import os
import re
import json
import qdarkstyle
from collections import defaultdict
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QComboBox,
    QProgressBar, QInputDialog, QFileDialog, QDialog, QLineEdit, QMessageBox, QListWidget,
    QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor

from youtube_handler import YouTubeHandler
from downloader import Downloader
from microplaylist_handler import MicroPlaylistHandler
from styling import STYLE_SHEET

# --- Worker Threads ---
class LoginThread(QThread):
    auth_finished = pyqtSignal(str)
    def __init__(self, youtube_handler):
        super().__init__()
        self.youtube_handler = youtube_handler
    def run(self):
        result = self.youtube_handler.authenticate()
        self.auth_finished.emit(result)

class FetchAllPlaylistsThread(QThread):
    fetch_finished = pyqtSignal(object)
    def __init__(self, youtube_handler):
        super().__init__()
        self.youtube_handler = youtube_handler
    def run(self):
        playlists = self.youtube_handler.get_all_user_playlists()
        self.fetch_finished.emit(playlists)

class SyncThread(QThread):
    sync_finished = pyqtSignal(dict)
    def __init__(self, youtube_handler, playlists_to_sync):
        super().__init__()
        self.youtube_handler = youtube_handler
        self.playlists_to_sync = playlists_to_sync
    def run(self):
        updated_playlists = {}
        for playlist_id, playlist_data in self.playlists_to_sync.items():
            is_private = playlist_data.get('is_private', False)
            new_data = self.youtube_handler.get_playlist_info(playlist_id, is_private)
            if new_data and 'error' not in new_data:
                updated_playlists[playlist_id] = new_data
                updated_playlists[playlist_id]['is_private'] = is_private
            QApplication.processEvents()
        self.sync_finished.emit(updated_playlists)

# --- Dialogs ---
class CreateMicroPlaylistDialog(QDialog):
    def __init__(self, parent_playlist_id, all_tracks, microplaylist_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Micro-Playlist")
        self.parent_playlist_id = parent_playlist_id
        self.microplaylist_handler = microplaylist_handler
        self.selected_artists = set()
        self.new_micro_playlist_name = ""

        all_artists = set()
        for track in all_tracks:
            for artist in track.get('artists', []):
                if 'name' in artist:
                    cleaned_name = artist['name'].replace(' - Topic', '').strip()
                    if cleaned_name:
                        all_artists.add(cleaned_name)

        self.all_artist_names = sorted(list(all_artists))

        self.layout = QVBoxLayout(self)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search for an artist...")
        self.search_bar.textChanged.connect(self.filter_artists)
        self.layout.addWidget(self.search_bar)
        
        self.layout.addWidget(QLabel("Select one or more artists:"))
        self.artist_list = QListWidget()
        self.artist_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.artist_list.addItems(self.all_artist_names)
        self.artist_list.itemSelectionChanged.connect(self.update_selection)
        self.layout.addWidget(self.artist_list)

        self.selected_label = QLabel("Selected: None")
        self.selected_label.setWordWrap(True)
        self.layout.addWidget(self.selected_label)

        self.layout.addWidget(QLabel("Micro-Playlist Name (optional):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Defaults to artist names")
        self.layout.addWidget(self.name_input)

        buttons_layout = QHBoxLayout()
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.create_and_close)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(create_button)
        buttons_layout.addWidget(cancel_button)
        self.layout.addLayout(buttons_layout)

    def update_selection(self):
        currently_selected_texts = {item.text() for item in self.artist_list.selectedItems()}
        currently_visible_texts = {self.artist_list.item(i).text() for i in range(self.artist_list.count())}
        
        self.selected_artists.update(currently_selected_texts)
        
        unselected_visible = currently_visible_texts - currently_selected_texts
        self.selected_artists.difference_update(unselected_visible)

        if self.selected_artists:
            self.selected_label.setText(f"Selected: {', '.join(sorted(list(self.selected_artists)))}")
        else:
            self.selected_label.setText("Selected: None")

    def filter_artists(self, text):
        self.artist_list.blockSignals(True)
        self.artist_list.clear()
        search_text = text.lower()
        
        filtered_artists = [artist for artist in self.all_artist_names if search_text in artist.lower()]
        self.artist_list.addItems(filtered_artists)

        for i in range(self.artist_list.count()):
            item = self.artist_list.item(i)
            if item.text() in self.selected_artists:
                item.setSelected(True)
        self.artist_list.blockSignals(False)

    def create_and_close(self):
        if not self.selected_artists:
            QMessageBox.warning(self, "Error", "Please select at least one artist.")
            return
        
        selected_artists = sorted(list(self.selected_artists))
        custom_name = self.name_input.text().strip()
        self.new_micro_playlist_name = custom_name if custom_name else ", ".join(selected_artists)

        if self.microplaylist_handler.add_microplaylist(self.parent_playlist_id, self.new_micro_playlist_name, selected_artists):
            self.accept()
        else:
            QMessageBox.warning(self, "Error", f"A micro-playlist named '{self.new_micro_playlist_name}' already exists.")

class EditMicroPlaylistDialog(QDialog):
    def __init__(self, parent_playlist_id, microplaylist, all_tracks, microplaylist_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Micro-Playlist")
        self.parent_playlist_id = parent_playlist_id
        self.original_name = microplaylist['name']
        self.microplaylist_handler = microplaylist_handler
        self.selected_artists = set(microplaylist.get('artists', []))
        
        all_artists = set()
        for track in all_tracks:
            for artist in track.get('artists', []):
                if 'name' in artist:
                    cleaned_name = artist['name'].replace(' - Topic', '').strip()
                    if cleaned_name:
                        all_artists.add(cleaned_name)
        self.all_artist_names = sorted(list(all_artists))

        self.layout = QVBoxLayout(self)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search for an artist...")
        self.search_bar.textChanged.connect(self.filter_artists)
        self.layout.addWidget(self.search_bar)
        
        self.layout.addWidget(QLabel("Select one or more artists:"))
        self.artist_list = QListWidget()
        self.artist_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.artist_list.addItems(self.all_artist_names)
        self.filter_artists("")
        self.artist_list.itemSelectionChanged.connect(self.update_selection)
        self.layout.addWidget(self.artist_list)

        self.selected_label = QLabel()
        self.selected_label.setWordWrap(True)
        self.update_selection()
        self.layout.addWidget(self.selected_label)

        self.layout.addWidget(QLabel("Micro-Playlist Name:"))
        self.name_input = QLineEdit()
        self.name_input.setText(self.original_name)
        self.layout.addWidget(self.name_input)

        buttons_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_and_close)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(save_button)
        buttons_layout.addWidget(cancel_button)
        self.layout.addLayout(buttons_layout)
    
    def update_selection(self):
        currently_selected_texts = {item.text() for item in self.artist_list.selectedItems()}
        currently_visible_texts = {self.artist_list.item(i).text() for i in range(self.artist_list.count())}
        
        self.selected_artists.update(currently_selected_texts)
        
        unselected_visible = currently_visible_texts - currently_selected_texts
        self.selected_artists.difference_update(unselected_visible)

        if self.selected_artists:
            self.selected_label.setText(f"Selected: {', '.join(sorted(list(self.selected_artists)))}")
        else:
            self.selected_label.setText("Selected: None")

    def filter_artists(self, text):
        self.artist_list.blockSignals(True)
        self.artist_list.clear()
        search_text = text.lower()
        
        filtered_artists = [artist for artist in self.all_artist_names if search_text in artist.lower()]
        self.artist_list.addItems(filtered_artists)

        for i in range(self.artist_list.count()):
            item = self.artist_list.item(i)
            if item.text() in self.selected_artists:
                item.setSelected(True)
        self.artist_list.blockSignals(False)
    
    def save_and_close(self):
        new_name = self.name_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Micro-playlist name cannot be empty.")
            return
        
        if not self.selected_artists:
            QMessageBox.warning(self, "Error", "Please select at least one artist.")
            return
        
        new_artists = sorted(list(self.selected_artists))
        
        success, message = self.microplaylist_handler.update_microplaylist(self.parent_playlist_id, self.original_name, new_name, new_artists)
        if success:
            self.accept()
        else:
            QMessageBox.warning(self, "Error", message)

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rekordbox YT Music Bridge")
        self.setGeometry(100, 100, 1200, 800)
        self.youtube_handler = YouTubeHandler()
        self.microplaylist_handler = MicroPlaylistHandler()
        self.playlists = {}
        self.downloader = None
        self.playlists_file = "playlists.json"
        self.config_file = "config.json"
        self.config = {}
        self.local_files = set()
        self.expanded_folders = set()
        
        self.setup_ui()
        self.load_config()
        self.scan_download_directory()
        self.load_playlists()
        self.update_login_button_state()
        if self.youtube_handler.is_authenticated():
            self.fetch_all_user_playlists()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        top_layout = QHBoxLayout()
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Playlists"))
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderHidden(True)
        self.playlist_tree.itemDoubleClicked.connect(self.sync_playlist_from_tree)
        self.playlist_tree.currentItemChanged.connect(self.display_tracks)
        left_layout.addWidget(self.playlist_tree)
        
        self.synced_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.synced_playlists_item.setText(0, "Synced Playlists")
        self.synced_playlists_item.setFlags(self.synced_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.user_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.user_playlists_item.setText(0, "My YouTube Playlists")
        self.user_playlists_item.setFlags(self.user_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        playlist_buttons_layout = QHBoxLayout()
        add_playlist_button = QPushButton("Add by URL")
        add_playlist_button.clicked.connect(self.add_playlist)
        remove_playlist_button = QPushButton("Remove Synced")
        remove_playlist_button.clicked.connect(self.remove_playlist)
        playlist_buttons_layout.addWidget(add_playlist_button)
        playlist_buttons_layout.addWidget(remove_playlist_button)
        left_layout.addLayout(playlist_buttons_layout)

        micro_buttons_layout = QHBoxLayout()
        self.create_micro_button = QPushButton("Create Micro")
        self.create_micro_button.clicked.connect(self.open_create_micro_dialog)
        self.create_micro_button.setEnabled(False)
        self.edit_micro_button = QPushButton("Edit Micro")
        self.edit_micro_button.clicked.connect(self.open_edit_micro_dialog)
        self.edit_micro_button.setEnabled(False)
        self.delete_micro_button = QPushButton("Delete Micro")
        self.delete_micro_button.clicked.connect(self.delete_micro_playlist)
        self.delete_micro_button.setEnabled(False)
        micro_buttons_layout.addWidget(self.create_micro_button)
        micro_buttons_layout.addWidget(self.edit_micro_button)
        micro_buttons_layout.addWidget(self.delete_micro_button)
        left_layout.addLayout(micro_buttons_layout)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Tracks"))
        self.tracks_tree = QTreeWidget()
        self.tracks_tree.setHeaderLabels(["Track", "Artist", "Status"])
        self.tracks_tree.setColumnWidth(0, 400)
        self.tracks_tree.setColumnWidth(1, 200)
        self.tracks_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tracks_tree.currentItemChanged.connect(self.update_micro_buttons_state)
        right_layout.addWidget(self.tracks_tree)
        top_layout.addWidget(left_panel, 1)
        top_layout.addWidget(right_panel, 3)
        
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        controls_layout = QHBoxLayout()
        self.login_logout_button = QPushButton()
        self.login_logout_button.clicked.connect(self.toggle_login_logout)
        controls_layout.addWidget(self.login_logout_button)
        
        controls_layout.addWidget(QLabel("Sort by:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Date Added", "Track Name", "Artist Name", "Upload Date"])
        controls_layout.addWidget(self.sort_combo)
        self.download_button = QPushButton("Download Selected")
        self.download_button.clicked.connect(self.start_download)
        controls_layout.addWidget(self.download_button)
        self.progress_bar = QProgressBar()
        bottom_layout.addLayout(controls_layout)
        bottom_layout.addWidget(self.progress_bar)
        estimates_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Idle")
        self.estimates_label = QLabel("Estimates: ~0 MB")
        estimates_layout.addWidget(self.status_label)
        estimates_layout.addStretch()
        estimates_layout.addWidget(self.estimates_label)
        bottom_layout.addLayout(estimates_layout)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(bottom_panel)

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {"download_directory": ""}
            self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def scan_download_directory(self):
        self.local_files.clear()
        download_dir = self.config.get("download_directory")
        if download_dir and os.path.exists(download_dir):
            for root, _, files in os.walk(download_dir):
                for file in files:
                    if file.endswith(".mp3"):
                        self.local_files.add(os.path.join(root, file))

    def is_track_downloaded(self, track, track_index, total_tracks, base_path):
        track_title = track.get('title', 'N/A')
        
        # Original artist names (including ' - Topic')
        artists_with_topic = [a['name'].strip() for a in track.get('artists', []) if 'name' in a]
        # Cleaned artist names (without ' - Topic')
        artists_without_topic = [name.replace(' - Topic', '').strip() for name in artists_with_topic]
        
        # Create comma-separated strings for both versions
        artists_str_with_topic = ', '.join(artists_with_topic)
        artists_str_without_topic = ', '.join(artists_without_topic)
        
        # List of artist strings to check
        artist_variations = list(set([artists_str_with_topic, artists_str_without_topic]))
        
        def sanitize_legacy(name):
            return "".join([c for c in name if c.isalpha() or c.isdigit() or c in (' ', '.', '_', '-', '(', ')', ',')]).rstrip()

        def sanitize_new(name):
            return re.sub(r'[\/*?:"<>|]', '_', name)

        for artists in artist_variations:
            for sort_option in ["Track Name", "Artist Name", "Upload Date", "Date Added"]:
                if sort_option == "Track Name":
                    filename_template = f"{track_title}_{artists}"
                elif sort_option == "Artist Name":
                    filename_template = f"{artists}_{track_title}"
                else:
                    num_digits = len(str(total_tracks))
                    filename_template = f"{str(track_index + 1).zfill(num_digits)}_{track_title}_{artists}"
                
                # Check against both old and new sanitization methods
                legacy_filename = sanitize_legacy(filename_template) + ".mp3"
                new_filename = sanitize_new(filename_template) + ".mp3"

                if os.path.join(base_path, legacy_filename) in self.local_files:
                    return True
                if os.path.join(base_path, new_filename) in self.local_files:
                    return True
        return False

    def open_create_micro_dialog(self):
        current_item = self.playlist_tree.currentItem()
        if not current_item or not current_item.data(0, Qt.ItemDataRole.UserRole): return
        
        item_type, playlist_id = current_item.data(0, Qt.ItemDataRole.UserRole)
        if item_type != 'playlist': return

        all_tracks = self.playlists.get(playlist_id, {}).get('tracks', [])
        dialog = CreateMicroPlaylistDialog(playlist_id, all_tracks, self.microplaylist_handler, self)
        if dialog.exec():
            self.refresh_playlist_tree() 
            self.display_tracks(current_item, None)
            
            new_name = dialog.new_micro_playlist_name
            iterator = QTreeWidgetItemIterator(self.tracks_tree)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == 'micro_folder' and data[1][1] == new_name:
                    self.tracks_tree.setCurrentItem(item)
                    break
                iterator += 1

    def open_edit_micro_dialog(self):
        current_track_item = self.tracks_tree.currentItem()
        if not current_track_item: return
        data = current_track_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != 'micro_folder': return
        
        parent_id, micro_name = data[1]
        
        microplaylist = None
        all_mps_for_parent = self.microplaylist_handler.get_microplaylists_for_playlist(parent_id)
        
        for mp in all_mps_for_parent:
            if isinstance(mp, dict) and mp.get('name') == micro_name:
                microplaylist = mp
                break
        
        if not microplaylist: return

        all_tracks = self.playlists.get(parent_id, {}).get('tracks', [])
        dialog = EditMicroPlaylistDialog(parent_id, microplaylist, all_tracks, self.microplaylist_handler, self)
        
        if dialog.exec():
            current_playlist_item = self.playlist_tree.currentItem()
            self.display_tracks(current_playlist_item, None)

    def delete_micro_playlist(self):
        current_track_item = self.tracks_tree.currentItem()
        if not current_track_item: return
        data = current_track_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != 'micro_folder': return
        parent_id, micro_name = data[1]
        reply = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete '{micro_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            self.microplaylist_handler.remove_microplaylist(parent_id, micro_name)
            self.display_tracks(self.playlist_tree.currentItem(), None)

    def refresh_playlist_tree(self):
        current_selection = self.playlist_tree.currentItem()
        selected_id = None
        if current_selection and current_selection.data(0, Qt.ItemDataRole.UserRole):
            _, selected_id = current_selection.data(0, Qt.ItemDataRole.UserRole)

        self.playlist_tree.clear()

        self.synced_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.synced_playlists_item.setText(0, "Synced Playlists")
        self.synced_playlists_item.setFlags(self.synced_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        self.user_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.user_playlists_item.setText(0, "My YouTube Playlists")
        self.user_playlists_item.setFlags(self.user_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        new_item_to_select = None
        for p_id, p_data in self.playlists.items():
            playlist_item = QTreeWidgetItem(self.synced_playlists_item)
            playlist_item.setText(0, p_data.get('title', 'Untitled Playlist'))
            playlist_item.setData(0, Qt.ItemDataRole.UserRole, ('playlist', p_id))
            if p_id == selected_id:
                new_item_to_select = playlist_item

        if self.youtube_handler.is_authenticated():
            self.fetch_all_user_playlists()
        
        self.playlist_tree.expandAll()
        if new_item_to_select:
            self.playlist_tree.setCurrentItem(new_item_to_select)

    def update_micro_buttons_state(self, current_item, previous_item):
        is_micro_folder = False
        if current_item:
            data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'micro_folder':
                is_micro_folder = True
        
        self.edit_micro_button.setEnabled(is_micro_folder)
        self.delete_micro_button.setEnabled(is_micro_folder)

    def display_tracks(self, current, previous):
        is_synced_playlist = current is not None and current.parent() == self.synced_playlists_item
        self.create_micro_button.setEnabled(is_synced_playlist)
        self.edit_micro_button.setEnabled(False)
        self.delete_micro_button.setEnabled(False)
        self.tracks_tree.clear()
        
        if not current or not current.data(0, Qt.ItemDataRole.UserRole): return
        
        item_type, p_id = current.data(0, Qt.ItemDataRole.UserRole)
        if item_type != 'playlist': return

        self.scan_download_directory()

        all_playlist_tracks = self.playlists.get(p_id, {}).get('tracks', [])
        total_tracks = len(all_playlist_tracks)

        micro_tracks_map, remaining_tracks_map = self.microplaylist_handler.segregate_tracks(self.playlists)
        
        seen_video_ids = set()

        download_dir = self.config.get("download_directory")
        playlist_name = self.playlists.get(p_id, {}).get('title', 'Untitled')
        sanitized_playlist_name = self.sanitize_filename(playlist_name)

        def add_track_to_tree(parent_item, track, track_index, base_path):
            if track['videoId'] in seen_video_ids:
                return
            seen_video_ids.add(track['videoId'])
            
            track_item = QTreeWidgetItem(parent_item)
            track_item.setText(0, track.get('title', 'N/A'))
            artists = ", ".join([a['name'].replace(' - Topic', '').strip() for a in track.get('artists', []) if 'name' in a])
            track_item.setText(1, artists)
            
            status = "Downloaded" if self.is_track_downloaded(track, track_index, total_tracks, base_path) else "Not Downloaded"
            track_item.setText(2, status)
            track_item.setData(0, Qt.ItemDataRole.UserRole, ('track', track))

        parent_microplaylists = self.microplaylist_handler.get_microplaylists_for_playlist(p_id)
        valid_mps = [mp for mp in parent_microplaylists if isinstance(mp, dict)]
        
        track_counter = 0
        for mp in sorted(valid_mps, key=lambda x: x['name']):
            folder_item = QTreeWidgetItem(self.tracks_tree)
            folder_item.setText(0, f"📁 {mp['name']}")
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ('micro_folder', (p_id, mp['name'])))
            tracks_in_folder = micro_tracks_map.get((p_id, mp['name']), [])
            
            sanitized_micro_name = self.sanitize_filename(mp['name'])
            micro_base_path = os.path.join(download_dir, sanitized_playlist_name, sanitized_micro_name)

            for track in tracks_in_folder:
                add_track_to_tree(folder_item, track, track_counter, micro_base_path)
                track_counter += 1

        playlist_base_path = os.path.join(download_dir, sanitized_playlist_name)
        for track in remaining_tracks_map.get(p_id, []):
            add_track_to_tree(self.tracks_tree, track, track_counter, playlist_base_path)
            track_counter += 1

    def start_download(self):
        selected_items = self.tracks_tree.selectedItems()
        if not selected_items: return
        
        output_dir = self.config.get("download_directory")
        if not output_dir or not os.path.exists(output_dir):
            output_dir = QFileDialog.getExistingDirectory(self, "Select Download Directory")
            if not output_dir: return
            self.config["download_directory"] = output_dir
            self.save_config()
            self.scan_download_directory()
        
        self.expanded_folders.clear()
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == 'micro_folder':
                    self.expanded_folders.add(data[1])
            iterator += 1

        tracks_to_download_info = []
        unique_ids = set()
        
        current_playlist_item = self.playlist_tree.currentItem()
        if not current_playlist_item or not current_playlist_item.data(0, Qt.ItemDataRole.UserRole): return
        
        _, p_id = current_playlist_item.data(0, Qt.ItemDataRole.UserRole)
        all_playlist_tracks = self.playlists.get(p_id, {}).get('tracks', [])
        total_tracks = len(all_playlist_tracks)

        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data: continue
            
            item_type, item_data = data
            
            def process_track(track_data, path=''):
                video_id = track_data['videoId']
                if video_id not in unique_ids:
                    track_index = next((i for i, t in enumerate(all_playlist_tracks) if t['videoId'] == video_id), -1)
                    
                    if not self.is_track_downloaded(track_data, track_index, total_tracks, path):
                        tracks_to_download_info.append({'data': track_data, 'path': path})
                        unique_ids.add(video_id)

            if item_type == 'track':
                # Determine path for individual track
                parent = item.parent()
                base_path = ""
                playlist_name = self.playlists[p_id]['title']
                sanitized_playlist_name = self.sanitize_filename(playlist_name)
                
                if parent and parent.data(0, Qt.ItemDataRole.UserRole) and parent.data(0, Qt.ItemDataRole.UserRole)[0] == 'micro_folder':
                    _, micro_name = parent.data(0, Qt.ItemDataRole.UserRole)[1]
                    sanitized_micro_name = self.sanitize_filename(micro_name)
                    base_path = os.path.join(output_dir, sanitized_playlist_name, sanitized_micro_name)
                else:
                    base_path = os.path.join(output_dir, sanitized_playlist_name)
                process_track(item_data, base_path)

            elif item_type == 'micro_folder':
                parent_id, micro_name = item_data
                playlist_name = self.playlists[parent_id]['title']
                micro_path = os.path.join(output_dir, self.sanitize_filename(playlist_name), self.sanitize_filename(micro_name))
                for i in range(item.childCount()):
                    child = item.child(i)
                    _, track_data = child.data(0, Qt.ItemDataRole.UserRole)
                    process_track(track_data, micro_path)

        if not tracks_to_download_info: 
            self.status_label.setText("All selected songs are already downloaded.")
            return

        final_tracks_with_paths = []
        for track_info in tracks_to_download_info:
            download_path = track_info['path']
            if not download_path:
                if current_playlist_item and current_playlist_item.data(0, Qt.ItemDataRole.UserRole):
                    item_type, p_id = current_playlist_item.data(0, Qt.ItemDataRole.UserRole)
                    if item_type == 'playlist':
                        playlist_name = self.playlists[p_id]['title']
                        download_path = os.path.join(output_dir, self.sanitize_filename(playlist_name))
            
            if not download_path: download_path = output_dir

            if not os.path.exists(download_path):
                os.makedirs(download_path, exist_ok=True)
            final_tracks_with_paths.append({'data': track_info['data'], 'path': download_path})

        tracks = [ft['data'] for ft in final_tracks_with_paths]
        paths = [ft['path'] for ft in final_tracks_with_paths]

        self.downloader = Downloader(tracks, paths, self.sort_combo.currentText())
        self.downloader.progress_update.connect(self.update_track_status)
        self.downloader.estimation_update.connect(self.update_estimates)
        self.downloader.download_finished.connect(self.on_download_finished)
        self.downloader.all_downloads_finished.connect(self.on_all_downloads_finished)
        self.downloader.start()
        self.status_label.setText(f"Starting download of {len(tracks)} track(s)...")

    def sanitize_filename(self, name):
        return re.sub(r'[\/*?:"<>|]', "", name)

    def load_playlists(self):
        if os.path.exists(self.playlists_file):
            with open(self.playlists_file, 'r') as f:
                self.playlists = json.load(f)
            self.refresh_playlist_tree()
            self.check_for_updates()

    def save_playlists(self):
        with open(self.playlists_file, 'w') as f:
            json.dump(self.playlists, f, indent=4)

    def toggle_login_logout(self):
        if self.youtube_handler.is_authenticated(): self.logout()
        else: self.login()
    
    def update_login_button_state(self):
        self.login_logout_button.setText("Logout" if self.youtube_handler.is_authenticated() else "Login with Google")

    def login(self):
        self.status_label.setText("Attempting to log in...")
        self.login_thread = LoginThread(self.youtube_handler)
        self.login_thread.auth_finished.connect(self.on_login_finished)
        self.login_thread.start()

    def on_login_finished(self, result):
        self.status_label.setText(result)
        self.update_login_button_state()
        if "successful" in result: self.fetch_all_user_playlists()

    def logout(self):
        self.youtube_handler.logout()
        self.update_login_button_state()
        self.status_label.setText("Logged out.")
        self.refresh_playlist_tree()

    def fetch_all_user_playlists(self):
        self.status_label.setText("Fetching your YouTube playlists...")
        self.fetch_playlists_thread = FetchAllPlaylistsThread(self.youtube_handler)
        self.fetch_playlists_thread.fetch_finished.connect(self.populate_user_playlists)
        self.fetch_playlists_thread.start()

    def populate_user_playlists(self, user_playlists):
        self.user_playlists_item.takeChildren()
        if isinstance(user_playlists, dict) and 'error' in user_playlists:
            self.status_label.setText(f"Error: {user_playlists['error']}")
            return
        grey_brush = QBrush(QColor("grey"))
        for playlist in user_playlists:
            if playlist['id'] not in self.playlists:
                item = QTreeWidgetItem(self.user_playlists_item)
                icon = {"public": "👁️", "private": "🔒", "unlisted": "🔗"}.get(playlist['privacyStatus'], "")
                item.setText(0, f"{icon} {playlist['title']}")
                item.setData(0, Qt.ItemDataRole.UserRole, playlist)
                item.setForeground(0, grey_brush)
        self.status_label.setText("Fetched playlists. Double-click to sync.")
        self.playlist_tree.expandAll()

    def sync_playlist_from_tree(self, item, column):
        if item.parent() == self.user_playlists_item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            pid = data['id']
            is_private = data['privacyStatus'] != 'public'
            self.status_label.setText(f"Fetching full data for {data['title']}...")
            QApplication.processEvents()
            full_data = self.youtube_handler.get_playlist_info(pid, is_private)
            if full_data and 'error' not in full_data:
                full_data['is_private'] = is_private
                self.playlists[pid] = full_data
                self.save_playlists()
                self.refresh_playlist_tree()
                self.status_label.setText(f"Synced: {full_data['title']}")
            else:
                self.status_label.setText(f"Error: {full_data.get('error', 'Unknown')}")

    def add_playlist(self):
        url, ok = QInputDialog.getText(self, 'Add Playlist by URL', 'URL:')
        if ok and url:
            pid = self.extract_playlist_id(url)
            if pid:
                self.status_label.setText(f"Fetching: {pid}...")
                data = self.youtube_handler.get_playlist_info(pid, is_private=False)
                if data and 'error' not in data:
                    data['is_private'] = False
                    self.playlists[pid] = data
                    self.save_playlists()
                    self.refresh_playlist_tree()
                else: self.status_label.setText("Error: Could not fetch playlist.")
            else: self.status_label.setText("Error: Invalid URL.")

    def remove_playlist(self):
        current = self.playlist_tree.currentItem()
        if current and current.parent() == self.synced_playlists_item:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'playlist':
                pid = data[1]
                if pid in self.playlists:
                    del self.playlists[pid]
                    if pid in self.microplaylist_handler.microplaylists:
                        del self.microplaylist_handler.microplaylists[pid]
                        self.microplaylist_handler.save_microplaylists()
                    self.save_playlists()
                    self.refresh_playlist_tree()
                    self.tracks_tree.clear()

    def check_for_updates(self):
        self.status_label.setText("Checking for updates...")
        self.sync_thread = SyncThread(self.youtube_handler, self.playlists)
        self.sync_thread.sync_finished.connect(self.on_sync_finished)
        self.sync_thread.start()

    def on_sync_finished(self, updated_data):
        summary = []
        for pid, new_data in updated_data.items():
            if pid in self.playlists:
                old_ids = {t['videoId'] for t in self.playlists[pid].get('tracks', [])}
                new_ids = {t['videoId'] for t in new_data.get('tracks', [])}
                count = len(new_ids - old_ids)
                if count > 0:
                    summary.append(f"'{new_data.get('title', '...')[:30]}...': {count} new song(s)")
            self.playlists[pid] = new_data
            QApplication.processEvents()
        if summary:
            QMessageBox.information(self, "Updates Found", "\n".join(summary))
        self.status_label.setText("Sync complete.")
        self.save_playlists()
        self.refresh_playlist_tree()

    def update_track_status(self, video_id, status, percentage):
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'track' and data[1]['videoId'] == video_id:
                item.setText(2, f"{status} ({percentage}%)")
                break
            iterator += 1

    def on_download_finished(self, video_id, success, message):
        if success:
            self.scan_download_directory() # Re-scan to find the new file
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'track' and data[1]['videoId'] == video_id:
                item.setText(2, "Downloaded" if success else "Error")
                break
            iterator += 1
    
    def on_all_downloads_finished(self):
        self.status_label.setText("All downloads finished.")
        self.downloader = None
        current_playlist_item = self.playlist_tree.currentItem()
        self.display_tracks(current_playlist_item, None)
        
        # Restore expanded folders
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'micro_folder' and data[1] in self.expanded_folders:
                item.setExpanded(True)
            iterator += 1
        
        if current_playlist_item:
            self.playlist_tree.setCurrentItem(current_playlist_item)
    
    def update_estimates(self, time_str):
        self.estimates_label.setText(f"Estimates: {time_str}")

    def extract_playlist_id(self, url):
        match = re.search(r"list=([a-zA-Z0-9_-]+)", url)
        return match.group(1) if match else None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet() + STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
