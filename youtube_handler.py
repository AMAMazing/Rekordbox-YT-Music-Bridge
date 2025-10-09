import os
import pickle
from ytmusicapi import YTMusic
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class YouTubeHandler:
    def __init__(self):
        self.ytmusic = YTMusic()
        self.credentials = None
        self.api_service = None
        self.scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        self.client_secrets_file = "client_secrets.json"
        self.token_pickle_file = "token.pickle"
        # Try to load existing credentials
        self.load_credentials()

    def load_credentials(self):
        if os.path.exists(self.token_pickle_file):
            with open(self.token_pickle_file, "rb") as token:
                self.credentials = pickle.load(token)
            if self.credentials and self.credentials.valid:
                self.api_service = build("youtube", "v3", credentials=self.credentials)
            elif self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                self.api_service = build("youtube", "v3", credentials=self.credentials)
                with open(self.token_pickle_file, "wb") as token:
                    pickle.dump(self.credentials, token)

    def is_authenticated(self):
        return self.api_service is not None

    def authenticate(self):
        if not os.path.exists(self.client_secrets_file):
            return "client_secrets.json not found."
        
        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
        self.credentials = flow.run_local_server(port=0)
        
        with open(self.token_pickle_file, "wb") as token:
            pickle.dump(self.credentials, token)
        
        self.api_service = build("youtube", "v3", credentials=self.credentials)
        return "Authentication successful."

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
            return playlist
        except Exception as e:
            return {"error": str(e)}

    def get_private_playlist_info(self, playlist_id):
        if not self.is_authenticated():
            return {"error": "User not authenticated. Please log in."}

        try:
            # First get playlist title
            playlist_request = self.api_service.playlists().list(part="snippet", id=playlist_id)
            playlist_response = playlist_request.execute()
            playlist_title = playlist_response["items"][0]["snippet"]["title"]

            # Then get all tracks
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
                    video_id = snippet["resourceId"]["videoId"]
                    title = snippet["title"]
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
