import os
import pickle
import httplib2
from ytmusicapi import YTMusic
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

httplib2.Http.DEFAULT_TIMEOUT = 300

class YouTubeHandler:
    def __init__(self):
        print("Initializing YouTubeHandler...")
        self.ytmusic = YTMusic()
        self.credentials = None
        self.api_service = None
        self.scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        self.client_secrets_file = "client_secrets.json"
        self.token_pickle_file = "token.pickle"
        self.load_credentials()
        print("YouTubeHandler initialized.")

    def load_credentials(self):
        print("Attempting to load credentials...")
        self.credentials = None
        self.api_service = None

        if os.path.exists(self.token_pickle_file):
            try:
                with open(self.token_pickle_file, "rb") as token:
                    self.credentials = pickle.load(token)
                print("Credentials loaded from token.pickle.")
            except (pickle.UnpicklingError, EOFError, ValueError) as e:
                print(f"Error loading token.pickle: {e}. The file might be corrupted. Deleting it.")
                os.remove(self.token_pickle_file)
                self.credentials = None

        if self.credentials:
            try:
                if self.credentials.expired and self.credentials.refresh_token:
                    print("Credentials expired. Attempting to refresh...")
                    self.credentials.refresh(Request())
                    with open(self.token_pickle_file, "wb") as token:
                        pickle.dump(self.credentials, token)
                    print("Credentials refreshed and saved.")
            except RefreshError:
                print("Token refresh failed. Deleting invalid token file.")
                if os.path.exists(self.token_pickle_file):
                    os.remove(self.token_pickle_file)
                self.credentials = None
            except Exception as e:
                print(f"An unexpected error occurred during credential refresh: {e}")
                self.credentials = None

            if self.credentials and self.credentials.valid:
                print("Credentials are valid. Building API service.")
                self.api_service = build("youtube", "v3", credentials=self.credentials)
            else:
                print("Credentials are not valid after check.")
                self.api_service = None
        else:
            print("No valid credentials found.")

    def is_authenticated(self):
        return self.api_service is not None

    def authenticate(self):
        if not os.path.exists(self.client_secrets_file):
            return "client_secrets.json not found."
        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
            self.credentials = flow.run_local_server(port=0)
            with open(self.token_pickle_file, "wb") as token:
                pickle.dump(self.credentials, token)
            self.api_service = build("youtube", "v3", credentials=self.credentials)
            return "Authentication successful."
        except Exception as e:
            return f"Authentication failed: {e}"

    def logout(self):
        if os.path.exists(self.token_pickle_file):
            os.remove(self.token_pickle_file)
        self.credentials = None
        self.api_service = None

    def get_all_user_playlists(self):
        if not self.is_authenticated():
            return {"error": "User not authenticated."}
        playlists = []
        next_page_token = None
        while True:
            try:
                request = self.api_service.playlists().list(
                    part="snippet,status",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
                for item in response.get("items", []):
                    playlists.append({
                        "id": item["id"],
                        "title": item["snippet"]["title"],
                        "privacyStatus": item["status"]["privacyStatus"]
                    })
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break
            except Exception as e:
                return {"error": str(e)}
        return playlists

    def get_playlist_info(self, playlist_id, is_private=False):
        if is_private:
            return self.get_private_playlist_info(playlist_id)
        else:
            return self.get_public_playlist_info(playlist_id)

    def get_public_playlist_info(self, playlist_id):
        try:
            playlist = self.ytmusic.get_playlist(playlistId=playlist_id, limit=None)
            if playlist is None:
                return {"error": "Playlist not found or is private."}
            return playlist
        except Exception as e:
            return {"error": str(e)}

    def get_private_playlist_info(self, playlist_id):
        if not self.is_authenticated():
            return {"error": "User not authenticated. Please log in."}
        try:
            playlist_request = self.api_service.playlists().list(part="snippet", id=playlist_id)
            playlist_response = playlist_request.execute()
            if not playlist_response.get("items"):
                return {"error": "Private playlist not found. Check the ID and your permissions."}
            playlist_title = playlist_response["items"][0]["snippet"]["title"]
            tracks = []
            next_page_token = None
            while True:
                playlist_items_request = self.api_service.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                playlist_items_response = playlist_items_request.execute()
                for item in playlist_items_response["items"]:
                    snippet = item["snippet"]
                    video_id = snippet.get("resourceId", {}).get("videoId")
                    if not video_id:
                        continue
                    title = snippet.get("title", "N/A")
                    if title in ["Private video", "Deleted video"]:
                        continue
                    tracks.append({
                        "videoId": video_id,
                        "title": title,
                        "artists": [{"name": snippet.get("videoOwnerChannelTitle", "N/A")}]
                    })
                next_page_token = playlist_items_response.get("nextPageToken")
                if not next_page_token:
                    break
            return {"title": playlist_title, "tracks": tracks}
        except Exception as e:
            return {"error": str(e)}
