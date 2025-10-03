#!/usr/bin/env python3
"""
Object Storage utility for Replit App Storage
Adapted from blueprint:javascript_object_storage for Python
"""

import os
import json
import requests
from google.cloud import storage
from google.auth import credentials
from google.auth.transport import requests as google_requests
from uuid import uuid4

REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"

class ReplitObjectStorageCredentials(credentials.Credentials):
    """Custom credentials class for Replit object storage"""
    
    def __init__(self):
        super().__init__()
        self.token = None
        self.expiry = None
    
    def refresh(self, request):
        """Fetch access token from Replit sidecar"""
        response = requests.get(f"{REPLIT_SIDECAR_ENDPOINT}/credential")
        response.raise_for_status()
        data = response.json()
        self.token = data.get('access_token')
    
    @property
    def valid(self):
        return self.token is not None
    
    @property
    def expired(self):
        return False

class ObjectStorageService:
    """Service for interacting with Replit Object Storage"""
    
    def __init__(self):
        # Initialize Google Cloud Storage client with Replit credentials
        creds = ReplitObjectStorageCredentials()
        creds.refresh(None)
        self.client = storage.Client(
            credentials=creds,
            project=""
        )
        
        # Get bucket name from environment
        self.bucket_name = os.environ.get('OBJECT_STORAGE_BUCKET')
        if not self.bucket_name:
            raise ValueError(
                "OBJECT_STORAGE_BUCKET not set. Create a bucket in Object Storage "
                "and set the OBJECT_STORAGE_BUCKET environment variable."
            )
        
        self.bucket = self.client.bucket(self.bucket_name)
    
    def upload_file(self, file_data, object_name):
        """Upload file to object storage"""
        blob = self.bucket.blob(object_name)
        blob.upload_from_string(file_data)
        # Make the blob publicly accessible
        blob.make_public()
        return blob.public_url
    
    def delete_file(self, object_name):
        """Delete file from object storage"""
        blob = self.bucket.blob(object_name)
        blob.delete()
    
    def get_public_url(self, object_name):
        """Get public URL for an object"""
        blob = self.bucket.blob(object_name)
        return blob.public_url
    
    def upload_template_images(self, slug, square_data=None, story_data=None):
        """Upload template images and return their public URLs"""
        urls = {}
        
        if square_data:
            square_name = f"templates/{slug}/square.png"
            urls['square'] = self.upload_file(square_data, square_name)
        
        if story_data:
            story_name = f"templates/{slug}/story.png"
            urls['story'] = self.upload_file(story_data, story_name)
        
        return urls
    
    def delete_template(self, slug):
        """Delete all template files for a given slug"""
        # Delete square and story images and meta.json
        try:
            self.delete_file(f"templates/{slug}/square.png")
        except Exception as e:
            print(f"Warning: Could not delete square.png for {slug}: {e}")
        
        try:
            self.delete_file(f"templates/{slug}/story.png")
        except Exception as e:
            print(f"Warning: Could not delete story.png for {slug}: {e}")
        
        try:
            self.delete_file(f"templates/{slug}/meta.json")
        except Exception as e:
            print(f"Warning: Could not delete meta.json for {slug}: {e}")
