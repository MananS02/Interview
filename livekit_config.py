"""
LiveKit Configuration and Utilities
Handles LiveKit server connection, room creation, and token generation
"""

import os
import logging
from typing import Optional
from datetime import timedelta
from livekit import api
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# LiveKit server configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


class LiveKitManager:
    """Manager for LiveKit operations"""
    
    def __init__(self):
        if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
            logger.warning("LiveKit credentials not configured. Please set LIVEKIT_API_KEY and LIVEKIT_API_SECRET in .env")
        
        # For LiveKit Cloud, convert WSS URL to HTTPS API endpoint
        # wss://voice-01bwwyha.livekit.cloud -> https://voice-01bwwyha.livekit.cloud
        api_url = LIVEKIT_URL.replace("wss://", "https://").replace("ws://", "http://")
        
        self.url = api_url  # API endpoint for server-side operations
        self.ws_url = LIVEKIT_URL  # WebSocket URL for client connections
        self.api_key = LIVEKIT_API_KEY
        self.api_secret = LIVEKIT_API_SECRET
        
        logger.info(f"LiveKit configured - API: {self.url}, WebSocket: {self.ws_url}")
    
    async def create_room(self, room_name: str, empty_timeout: int = 300, max_participants: int = 2) -> dict:
        """
        Create a new LiveKit room for an interview session
        
        Args:
            room_name: Unique room identifier (typically session_id)
            empty_timeout: Seconds before empty room is deleted (default 5 minutes)
            max_participants: Maximum participants allowed (default 2: interviewer bot + candidate)
        
        Returns:
            dict: Room information
        """
        try:
            livekit_api = api.LiveKitAPI(
                url=self.url,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            room = await livekit_api.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=empty_timeout,
                    max_participants=max_participants,
                )
            )
            
            logger.info(f"Created LiveKit room: {room_name}")
            return {
                "sid": room.sid,
                "name": room.name,
                "empty_timeout": room.empty_timeout,
                "max_participants": room.max_participants,
                "creation_time": room.creation_time,
            }
        except Exception as e:
            logger.error(f"Failed to create LiveKit room {room_name}: {e}")
            raise
    
    def generate_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: Optional[str] = None,
        can_publish: bool = True,
        can_subscribe: bool = True,
        can_publish_data: bool = True,
        ttl: int = 3600
    ) -> str:
        """
        Generate an access token for a participant to join a room
        
        Args:
            room_name: Room to join
            participant_identity: Unique identifier for participant
            participant_name: Display name for participant
            can_publish: Allow publishing audio/video tracks
            can_subscribe: Allow subscribing to tracks
            can_publish_data: Allow publishing data messages
            ttl: Token time-to-live in seconds (default 1 hour)
        
        Returns:
            str: JWT access token
        """
        try:
            token = api.AccessToken(self.api_key, self.api_secret)
            token.with_identity(participant_identity)
            if participant_name:
                token.with_name(participant_name)
            
            # Set room permissions
            token.with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=can_publish,
                    can_subscribe=can_subscribe,
                    can_publish_data=can_publish_data,
                )
            )
            
            # Set token expiration
            token.with_ttl(timedelta(seconds=ttl))
            
            jwt_token = token.to_jwt()
            logger.info(f"Generated token for {participant_identity} in room {room_name}")
            return jwt_token
        except Exception as e:
            logger.error(f"Failed to generate token: {e}")
            raise
    
    async def delete_room(self, room_name: str) -> bool:
        """
        Delete a LiveKit room
        
        Args:
            room_name: Room to delete
        
        Returns:
            bool: True if successful
        """
        try:
            livekit_api = api.LiveKitAPI(
                url=self.url,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            await livekit_api.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            
            logger.info(f"Deleted LiveKit room: {room_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete room {room_name}: {e}")
            return False
    
    async def list_rooms(self) -> list:
        """
        List all active LiveKit rooms
        
        Returns:
            list: List of room information
        """
        try:
            livekit_api = api.LiveKitAPI(
                url=self.url,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            rooms = await livekit_api.room.list_rooms(api.ListRoomsRequest())
            
            return [
                {
                    "sid": room.sid,
                    "name": room.name,
                    "num_participants": room.num_participants,
                    "creation_time": room.creation_time,
                }
                for room in rooms
            ]
        except Exception as e:
            logger.error(f"Failed to list rooms: {e}")
            return []


# Global LiveKit manager instance
livekit_manager = LiveKitManager()


async def test_connection():
    """Test LiveKit server connection"""
    try:
        rooms = await livekit_manager.list_rooms()
        logger.info(f"✅ LiveKit connection successful. Found {len(rooms)} active rooms.")
        return True
    except Exception as e:
        logger.error(f"❌ LiveKit connection failed: {e}")
        return False
