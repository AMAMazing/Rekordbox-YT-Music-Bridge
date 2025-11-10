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
    QTreeWidgetItemIterator, QDialogButtonBox, QRadioButton, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices

from youtube_handler import YouTubeHandler
from microplaylist_handler import MicroPlaylistHandler
from file_manager import FileManager
from download_handler import DownloadHandler
from track_checker import TrackChecker
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

class FullSyncThread(QThread):
    sync_finished = pyqtSignal(dict, list)

    def __init__(self, youtube_handler, playlists_to_sync):
        super().__init__()
        self.youtube_handler = youtube_handler
        self.playlists_to_sync = playlists_to_sync

    def run(self):
        live_user_playlists = self.youtube_handler.get_all_user_playlists()
        if 'error' in live_user_playlists:
            self.sync_finished.emit({}, [f"Error fetching playlists: {live_user_playlists['error']}"])
            return
            
        live_playlist_map = {p['id']: p for p in live_user_playlists}
        updated_playlists = {}
        summary = []
        
        for playlist_id, old_playlist_data in self.playlists_to_sync.items():
            if playlist_id not in live_playlist_map:
                summary.append(f"'{old_playlist_data.get('title', '...')}'': Skipped (not found in your account).")
                continue

            live_data = live_playlist_map[playlist_id]
            is_now_private = live_data['privacyStatus'] != 'public'
            
            new_data = self.youtube_handler.get_playlist_info(playlist_id, is_now_private)
            
            if new_data and 'error' not in new_data:
                old_ids = {t['videoId'] for t in old_playlist_data.get('tracks', [])}
                new_ids = {t['videoId'] for t in new_data.get('tracks', [])}
                count = len(new_ids - old_ids)
                if count > 0:
                    summary.append(f"'{new_data.get('title', '...')[:30]}...': {count} new song(s)")

                new_data['is_private'] = is_now_private
                updated_playlists[playlist_id] = new_data
            else:
                summary.append(f"'{old_playlist_data.get('title', '...')}'': Failed to sync.")
            
            QApplication.processEvents()
            
        self.sync_finished.emit(updated_playlists, summary)


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

class SettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = current_config.copy() 
        self.layout = QVBoxLayout(self)

        dir_layout = QHBoxLayout()
        self.dir_label = QLineEdit(self.config.get("download_directory", ""))
        self.dir_label.setReadOnly(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(QLabel("Download Directory:"))
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(browse_button)
        self.layout.addLayout(dir_layout)
        
        numbering_group = QGroupBox("Filename Numbering")
        num_layout = QVBoxLayout()
        self.rb_num_none = QRadioButton("None")
        self.rb_num_playlist = QRadioButton("Playlist Order (e.g., 01_..., 02_...)")
        self.rb_num_release = QRadioButton("Release Year (e.g., 2023_...)")
        num_layout.addWidget(self.rb_num_none)
        num_layout.addWidget(self.rb_num_playlist)
        num_layout.addWidget(self.rb_num_release)
        numbering_group.setLayout(num_layout)
        self.layout.addWidget(numbering_group)

        order_group = QGroupBox("Filename Name Order")
        order_layout = QVBoxLayout()
        self.rb_order_track_artist = QRadioButton("Track Name - Artist Name")
        self.rb_order_artist_track = QRadioButton("Artist Name - Track Name")
        order_layout.addWidget(self.rb_order_track_artist)
        order_layout.addWidget(self.rb_order_artist_track)
        order_group.setLayout(order_layout)
        self.layout.addWidget(order_group)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

        self.load_settings()

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if directory:
            self.dir_label.setText(directory)
            self.config["download_directory"] = directory

    def load_settings(self):
        num_setting = self.config.get("numbering", "playlist_order")
        if num_setting == "none": self.rb_num_none.setChecked(True)
        elif num_setting == "release_year": self.rb_num_release.setChecked(True)
        else: self.rb_num_playlist.setChecked(True)
        
        order_setting = self.config.get("name_order", "track_artist")
        if order_setting == "artist_track": self.rb_order_artist_track.setChecked(True)
        else: self.rb_order_track_artist.setChecked(True)

    def accept(self):
        if self.rb_num_none.isChecked(): self.config["numbering"] = "none"
        elif self.rb_num_release.isChecked(): self.config["numbering"] = "release_year"
        else: self.config["numbering"] = "playlist_order"
        
        if self.rb_order_artist_track.isChecked(): self.config["name_order"] = "artist_track"
        else: self.config["name_order"] = "track_artist"
        
        super().accept()

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        print("MainWindow __init__ started.")
        self.setWindowTitle("Rekordbox YT Music Bridge")
        self.setGeometry(100, 100, 1200, 800)
        
        print("Initializing handlers...")
        self.youtube_handler = YouTubeHandler()
        print("YouTubeHandler initialized.")
        self.microplaylist_handler = MicroPlaylistHandler()
        print("MicroPlaylistHandler initialized.")

        self.playlists = {}
        self.downloader = None
        self.playlists_file = "playlists.json"
        self.config_file = "config.json"
        self.config = {}
        self.expanded_folders = set()
        
        print("Loading config...")
        self.load_config()
        print("Config loaded.")

        self.file_manager = FileManager(self.config)
        print("FileManager initialized.")
        self.track_checker = TrackChecker(self.file_manager, self.config.get("download_directory"))
        print("TrackChecker initialized.")

        print("Setting up UI...")
        self.setup_ui()
        print("UI setup finished.")

        print("Loading playlists...")
        self.load_playlists()
        print("Playlists loaded.")

        self.update_login_button_state()
        if self.youtube_handler.is_authenticated():
            self.fetch_all_user_playlists()
        print("MainWindow initialization finished.")

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

        tracks_header_layout = QHBoxLayout()
        tracks_header_layout.addWidget(QLabel("Tracks"))
        tracks_header_layout.addStretch()
        tracks_header_layout.addWidget(QLabel("Sort by:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Date Added", "Track Name", "Artist Name"])
        self.sort_combo.currentIndexChanged.connect(self.sort_and_redisplay_tracks)
        tracks_header_layout.addWidget(self.sort_combo)
        right_layout.addLayout(tracks_header_layout)

        self.tracks_tree = QTreeWidget()
        self.tracks_tree.setHeaderLabels(["Track", "Artist", "Status"])
        self.tracks_tree.setColumnWidth(0, 400)
        self.tracks_tree.setColumnWidth(1, 200)
        self.tracks_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tracks_tree.currentItemChanged.connect(self.update_micro_buttons_state)
        self.tracks_tree.itemDoubleClicked.connect(self.on_track_double_clicked)
        right_layout.addWidget(self.tracks_tree)
        top_layout.addWidget(left_panel, 1)
        top_layout.addWidget(right_panel, 3)
        
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        controls_layout = QHBoxLayout()
        self.login_logout_button = QPushButton()
        self.login_logout_button.clicked.connect(self.toggle_login_logout)
        
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.open_settings_dialog)

        reformat_button = QPushButton("Reformat Files")
        reformat_button.clicked.connect(self.reformat_filenames)
        
        self.full_refresh_button = QPushButton("Full Refresh")
        self.full_refresh_button.clicked.connect(self.start_full_sync)

        controls_layout.addWidget(self.login_logout_button)
        controls_layout.addWidget(settings_button)
        controls_layout.addWidget(reformat_button)
        controls_layout.addWidget(self.full_refresh_button)
        controls_layout.addStretch()

        self.logged_out_label = QLabel("Login to sync your YouTube playlists.")
        self.logged_out_label.setStyleSheet("color: #888;")
        controls_layout.addWidget(self.logged_out_label)
        
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
            self.config = {
                "download_directory": "",
                "numbering": "playlist_order",
                "name_order": "track_artist"
            }
            self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def on_track_double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_data = data

        if item_type == 'track':
            filepath = item_data.get('filepath')
            if filepath and os.path.exists(filepath):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(filepath)))
            else:
                self.status_label.setText("File not found. It might have been moved or deleted.")
        
        elif item_type == 'micro_folder':
            directory_to_open = None
            if item.childCount() > 0:
                for i in range(item.childCount()):
                    child_item = item.child(i)
                    child_data = child_item.data(0, Qt.ItemDataRole.UserRole)
                    if child_data and child_data[0] == 'track':
                        track_info = child_data[1]
                        if 'filepath' in track_info and os.path.exists(track_info['filepath']):
                            directory_to_open = os.path.dirname(track_info['filepath'])
                            break
            
            if directory_to_open and os.path.exists(directory_to_open):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(directory_to_open)))
            else:
                _, micro_name = item_data
                self.status_label.setText(f"No downloaded files in '{micro_name}' to locate folder.")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            old_config = self.config
            self.config = dialog.config
            self.save_config()
            self.file_manager.config = self.config

            if old_config.get("download_directory") != self.config.get("download_directory"):
                self.track_checker = TrackChecker(self.file_manager, self.config.get("download_directory"))

            current_playlist_item = self.playlist_tree.currentItem()
            if current_playlist_item:
                self.display_tracks(current_playlist_item, None)
            
            self.status_label.setText("Settings updated.")
            QMessageBox.information(self, "Settings Changed", 
                                    "Settings have been updated. If you changed the filename format, "
                                    "you may want to use the 'Reformat Files' button.")

    def reformat_filenames(self):
        current_item = self.playlist_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Playlist Selected", "Please select a synced playlist to reformat.")
            return

        user_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) != 2 or user_data[0] != 'playlist':
            QMessageBox.warning(self, "No Playlist Selected", "Please select a synced playlist to reformat.")
            return
        
        item_type, p_id = user_data
            
        reply = QMessageBox.question(self, "Confirm Reformat", 
                                     "This will rename all downloaded files in the selected playlist according to the current settings. "
                                     "This action cannot be undone. Are you sure you want to continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        self.status_label.setText("Reformatting files... Please wait.")
        QApplication.processEvents()

        playlist_info = self.playlists.get(p_id)
        if not playlist_info:
            return

        self.track_checker.rescan()
        renamed_count = 0
        error_count = 0

        for i, track_data in enumerate(playlist_info.get("tracks", [])):
            microplaylist_name = track_data.get('microplaylist_name')
            old_filepath = self.track_checker.is_downloaded(track_data, playlist_info, microplaylist_name)
            
            if old_filepath:
                new_filename = self.file_manager.get_filename(track_data, i + 1, len(playlist_info.get("tracks", [])))
                new_directory = os.path.dirname(old_filepath)
                new_filepath = os.path.join(new_directory, new_filename + '.mp3')

                if old_filepath != new_filepath:
                    try:
                        if not os.path.exists(new_filepath):
                            os.rename(old_filepath, new_filepath)
                            renamed_count += 1
                        else:
                            error_count += 1
                    except OSError:
                        error_count += 1
        
        self.track_checker.rescan()
        self.display_tracks(current_item, None)
        self.status_label.setText(f"Reformatting complete. Renamed: {renamed_count}, Errors: {error_count}")

    def open_create_micro_dialog(self):
        current_item = self.playlist_tree.currentItem()
        if not current_item: return
        
        user_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) != 2 or user_data[0] != 'playlist': return

        item_type, playlist_id = user_data

        all_tracks = self.playlists.get(playlist_id, {}).get('tracks', [])
        dialog = CreateMicroPlaylistDialog(playlist_id, all_tracks, self.microplaylist_handler, self)
        if dialog.exec():
            self.refresh_playlist_tree() 
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

        if current_selection:
            user_data = current_selection.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(user_data, tuple) and len(user_data) == 2 and user_data[0] == 'playlist':
                _, selected_id = user_data

        self.playlist_tree.clear()

        self.synced_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.synced_playlists_item.setText(0, "Synced Playlists")
        self.synced_playlists_item.setFlags(self.synced_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        self.user_playlists_item = QTreeWidgetItem(self.playlist_tree)
        self.user_playlists_item.setText(0, "My YouTube Playlists")
        self.user_playlists_item.setFlags(self.user_playlists_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        new_item_to_select = None
        for p_id, p_data in sorted(self.playlists.items(), key=lambda item: item[1].get('title', '').lower()):
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

    def sort_and_redisplay_tracks(self):
        current_item = self.playlist_tree.currentItem()
        if current_item:
            self.display_tracks(current_item, None)

    def display_tracks(self, current, previous):
        self.tracks_tree.clear()
        
        if not current:
            self.create_micro_button.setEnabled(False)
            return

        user_data = current.data(0, Qt.ItemDataRole.UserRole)
        is_synced_playlist = isinstance(user_data, tuple) and len(user_data) == 2 and user_data[0] == 'playlist'
        
        self.create_micro_button.setEnabled(is_synced_playlist)
        self.edit_micro_button.setEnabled(False)
        self.delete_micro_button.setEnabled(False)

        if not is_synced_playlist:
            return
        
        item_type, p_id = user_data
        
        self.track_checker.rescan()
        micro_tracks_map, remaining_tracks_map = self.microplaylist_handler.segregate_tracks(self.playlists)
        sort_key = self.sort_combo.currentText()

        def get_sort_key_func(track):
            if sort_key == "Track Name":
                return track.get('title', 'N/A').lower()
            elif sort_key == "Artist Name":
                artists = track.get('artists', [])
                if artists and artists[0] is not None:
                    return artists[0].get('name', 'N/A').lower()
                return 'N/A'
            return None

        def sort_tracks(tracks):
            if sort_key == "Date Added":
                return tracks
            else:
                return sorted(tracks, key=get_sort_key_func)

        seen_video_ids = set()

        def add_track_to_tree(parent_item, track, micro_name=None):
            if track.get('videoId') in seen_video_ids:
                return
            seen_video_ids.add(track.get('videoId'))
            
            track_item = QTreeWidgetItem(parent_item)
            track_item.setText(0, track.get('title', 'N/A'))
            artists = ", ".join([a['name'].replace(' - Topic', '').strip() for a in track.get('artists', []) if a and 'name' in a])
            track_item.setText(1, artists)
            
            playlist_info = self.playlists.get(p_id)
            matched_filepath = self.track_checker.is_downloaded(track, playlist_info, micro_name)

            if matched_filepath:
                status = "Downloaded"
                track['filepath'] = matched_filepath
            else:
                status = "Not Downloaded"

            track_item.setText(2, status)
            track_item.setData(0, Qt.ItemDataRole.UserRole, ('track', track))

        parent_microplaylists = self.microplaylist_handler.get_microplaylists_for_playlist(p_id)
        valid_mps = [mp for mp in parent_microplaylists if isinstance(mp, dict)]
        
        for mp in sorted(valid_mps, key=lambda x: x['name']):
            folder_item = QTreeWidgetItem(self.tracks_tree)
            folder_item.setText(0, f"📁 {mp['name']}")
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ('micro_folder', (p_id, mp['name'])))
            tracks_in_folder = micro_tracks_map.get((p_id, mp['name']), [])
            
            for track in sort_tracks(tracks_in_folder):
                add_track_to_tree(folder_item, track, mp['name'])

        for track in sort_tracks(remaining_tracks_map.get(p_id, [])):
            add_track_to_tree(self.tracks_tree, track)

    def start_download(self):
        selected_items = self.tracks_tree.selectedItems()
        if not selected_items: return
        
        download_dir = self.config.get("download_directory")
        if not download_dir or not os.path.exists(download_dir):
            QMessageBox.warning(self, "Directory Not Set", "Please set a valid download directory in Settings.")
            return

        self.expanded_folders.clear()
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == 'micro_folder':
                    self.expanded_folders.add(data[1])
            iterator += 1

        tracks_to_download = []
        unique_ids = set()
        
        current_playlist_item = self.playlist_tree.currentItem()
        if not current_playlist_item: return

        user_data = current_playlist_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) != 2 or user_data[0] != 'playlist': return

        item_type, p_id = user_data
        playlist_info = self.playlists.get(p_id)
        
        def process_track(track_data, micro_name=None):
            video_id = track_data.get('videoId')
            if video_id and video_id not in unique_ids:
                if not self.track_checker.is_downloaded(track_data, playlist_info, micro_name):
                    track_data['playlist_title'] = playlist_info.get('title')
                    track_data['microplaylist_title'] = micro_name
                    track_data['playlist_track_count'] = len(playlist_info.get('tracks', []))
                    tracks_to_download.append(track_data)
                    unique_ids.add(video_id)

        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data: continue
            
            item_type, item_data = data
            
            if item_type == 'track':
                parent = item.parent()
                micro_name = None
                if parent and parent.data(0, Qt.ItemDataRole.UserRole) and parent.data(0, Qt.ItemDataRole.UserRole)[0] == 'micro_folder':
                    _, micro_name = parent.data(0, Qt.ItemDataRole.UserRole)[1]
                process_track(item_data, micro_name)

            elif item_type == 'micro_folder':
                _, micro_name = item_data
                for i in range(item.childCount()):
                    child = item.child(i)
                    _, track_data = child.data(0, Qt.ItemDataRole.UserRole)
                    process_track(track_data, micro_name)

        if not tracks_to_download: 
            self.status_label.setText("All selected songs are already downloaded.")
            return

        self.downloader = DownloadHandler(tracks_to_download, self.file_manager, download_dir)
        self.downloader.progress_update.connect(self.update_track_status)
        self.downloader.estimation_update.connect(self.update_estimates)
        self.downloader.download_finished.connect(self.on_download_finished)
        self.downloader.all_downloads_finished.connect(self.on_all_downloads_finished)
        self.downloader.start()
        self.status_label.setText(f"Starting download of {len(tracks_to_download)} track(s)...")

    def load_playlists(self):
        if os.path.exists(self.playlists_file):
            with open(self.playlists_file, 'r', encoding='utf-8') as f:
                self.playlists = json.load(f)
            self.refresh_playlist_tree()

    def save_playlists(self):
        with open(self.playlists_file, 'w', encoding='utf-8') as f:
            json.dump(self.playlists, f, indent=4)

    def toggle_login_logout(self):
        if self.youtube_handler.is_authenticated(): self.logout()
        else: self.login()
    
    def update_login_button_state(self):
        is_auth = self.youtube_handler.is_authenticated()
        self.login_logout_button.setText("Logout" if is_auth else "Login with Google")
        self.logged_out_label.setVisible(not is_auth)
        self.user_playlists_item.setHidden(not is_auth)
        self.full_refresh_button.setEnabled(is_auth)

    def login(self):
        self.status_label.setText("Attempting to log in... Please follow the instructions in your browser.")
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
        sorted_playlists = sorted(user_playlists, key=lambda p: p.get('title', '').lower())
        for playlist in sorted_playlists:
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
            self.status_label.setText(f"Syncing {data['title']}...")
            QApplication.processEvents()

            full_data = self.youtube_handler.get_playlist_info(pid, is_private)
            if full_data and 'error' not in full_data:
                full_data['is_private'] = is_private
                self.playlists[pid] = full_data
                self.save_playlists()
                self.refresh_playlist_tree()
                self.status_label.setText(f"Synced: {full_data['title']}")
            else:
                self.status_label.setText(f"Error syncing playlist: {full_data.get('error', 'Unknown')}")

    def add_playlist(self):
        url, ok = QInputDialog.getText(self, 'Add Playlist by URL', 'URL:')
        if ok and url:
            pid = self.extract_playlist_id(url)
            if pid:
                if pid in self.playlists:
                    self.status_label.setText("This playlist is already synced.")
                    return
                self.status_label.setText(f"Fetching: {pid}...")
                data = self.youtube_handler.get_playlist_info(pid, is_private=False)
                if data and 'error' not in data:
                    data['is_private'] = False
                    self.playlists[pid] = data
                    self.save_playlists()
                    self.refresh_playlist_tree()
                else: self.status_label.setText("Error: Could not fetch playlist. It may be private.")
            else: self.status_label.setText("Error: Invalid URL.")

    def remove_playlist(self):
        current = self.playlist_tree.currentItem()
        if current and current.parent() == self.synced_playlists_item:
            user_data = current.data(0, Qt.ItemDataRole.UserRole)
            if user_data and user_data[0] == 'playlist':
                pid = user_data[1]
                playlist_title = self.playlists.get(pid, {}).get('title', 'this playlist')
                reply = QMessageBox.question(self, "Confirm Removal", f"Are you sure you want to remove '{playlist_title}' from the synced list?")
                if reply == QMessageBox.StandardButton.No:
                    return

                if pid in self.playlists:
                    del self.playlists[pid]
                if pid in self.microplaylist_handler.microplaylists:
                    del self.microplaylist_handler.microplaylists[pid]
                    self.microplaylist_handler.save_microplaylists()
                
                self.save_playlists()
                self.refresh_playlist_tree()
                self.tracks_tree.clear()

    def start_full_sync(self):
        if not self.youtube_handler.is_authenticated():
            self.status_label.setText("Please log in to run a full refresh.")
            return
        if not self.playlists:
            self.status_label.setText("No playlists to sync.")
            return
            
        self.status_label.setText("Starting full refresh... This may take a moment.")
        self.full_refresh_button.setEnabled(False)
        
        self.full_sync_thread = FullSyncThread(self.youtube_handler, self.playlists)
        self.full_sync_thread.sync_finished.connect(self.on_full_sync_finished)
        self.full_sync_thread.start()

    def on_full_sync_finished(self, updated_data, summary):
        self.playlists.update(updated_data)
        # Remove playlists that were not in the updated data (e.g., deleted online)
        current_ids = set(updated_data.keys())
        existing_ids = set(self.playlists.keys())
        for pid in existing_ids - current_ids:
            if pid in self.playlists:
                del self.playlists[pid]

        self.save_playlists()
        self.refresh_playlist_tree()
        self.full_refresh_button.setEnabled(True)
        self.status_label.setText("Full refresh complete.")

        if summary:
            QMessageBox.information(self, "Refresh Complete", "\\n".join(summary))
        else:
            QMessageBox.information(self, "Refresh Complete", "No new songs found, but playlist details have been updated.")

    def update_track_status(self, video_id, status, percentage):
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'track' and data[1].get('videoId') == video_id:
                item.setText(2, f"{status} ({percentage}%)")
                break
            iterator += 1

    def on_download_finished(self, video_id, success, message):
        iterator = QTreeWidgetItemIterator(self.tracks_tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'track' and data[1].get('videoId') == video_id:
                item.setText(2, "Downloaded" if success else f"Error: {message}")
                if success:
                    current_playlist_item = self.playlist_tree.currentItem()
                    self.display_tracks(current_playlist_item, None)
                break
            iterator += 1
    
    def on_all_downloads_finished(self):
        self.status_label.setText("All downloads finished.")
        self.downloader = None
        current_playlist_item = self.playlist_tree.currentItem()
        self.display_tracks(current_playlist_item, None)
        
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

    # --- NEW: Graceful Shutdown Method ---
    def closeEvent(self, event):
        """Ensure threads are stopped gracefully before the application closes."""
        running_threads = []
        
        # Check downloader thread
        if self.downloader and self.downloader.isRunning():
            # In a real-world app you might want to ask the user if they want to cancel downloads
            running_threads.append(self.downloader)

        # Check other utility threads
        if hasattr(self, 'login_thread') and self.login_thread.isRunning():
            running_threads.append(self.login_thread)
        if hasattr(self, 'fetch_playlists_thread') and self.fetch_playlists_thread.isRunning():
            running_threads.append(self.fetch_playlists_thread)
        if hasattr(self, 'full_sync_thread') and self.full_sync_thread.isRunning():
            running_threads.append(self.full_sync_thread)

        if running_threads:
            print("Waiting for background tasks to finish before closing...")
            self.status_label.setText("Finishing background tasks...")
            # Disable the main window to prevent user interaction during shutdown
            self.setEnabled(False)
            QApplication.processEvents()
            
            for thread in running_threads:
                thread.quit()
                thread.wait(5000) # Wait up to 5 seconds for each thread

        event.accept() # Now it's safe to close

if __name__ == "__main__":
    print("Starting application...")
    app = QApplication(sys.argv)
    print("QApplication created.")
    app.setStyleSheet(qdarkstyle.load_stylesheet() + STYLE_SHEET)
    print("Stylesheet set.")
    window = MainWindow()
    print("MainWindow created.")
    window.show()
    print("MainWindow shown.")
    exit_code = app.exec()
    print(f"Application finished with exit code {exit_code}.")
    sys.exit(exit_code)
