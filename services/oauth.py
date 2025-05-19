# backend/services/oauth.py

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, status
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

oauth = OAuth()

# Configure Google OAuth
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Configure Facebook OAuth
oauth.register(
    name='facebook',
    client_id=os.getenv('FACEBOOK_CLIENT_ID'),
    client_secret=os.getenv('FACEBOOK_CLIENT_SECRET'),
    access_token_url='https://graph.facebook.com/oauth/access_token',
    access_token_params=None,
    authorize_url='https://www.facebook.com/dialog/oauth',
    authorize_params=None,
    api_base_url='https://graph.facebook.com/',
    client_kwargs={'scope': 'email'},
)

class OAuthService:
    async def get_google_user_data(self, token) -> dict:
        try:
            resp = await oauth.google.parse_id_token(token)
            return {
                'email': resp.get('email'),
                'name': resp.get('name'),
                'oauth_id': resp.get('sub'),
                'picture': resp.get('picture')
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate Google credentials"
            )

    async def get_facebook_user_data(self, access_token) -> dict:
        try:
            resp = await oauth.facebook.get(
                'me?fields=id,name,email,picture',
                token=access_token
            )
            user_data = resp.json()
            return {
                'email': user_data.get('email'),
                'name': user_data.get('name'),
                'oauth_id': user_data.get('id'),
                'picture': user_data.get('picture', {}).get('data', {}).get('url')
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate Facebook credentials"
            )

oauth_service = OAuthService()