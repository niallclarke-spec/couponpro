#!/usr/bin/env python3
"""
Object Storage utility for Digital Ocean Spaces
S3-compatible object storage that works anywhere
"""

import os
import boto3
from botocore.client import Config

class ObjectStorageService:
    """Service for interacting with Digital Ocean Spaces (S3-compatible)"""
    
    def __init__(self):
        # Get configuration from environment variables
        self.access_key = os.environ.get('SPACES_ACCESS_KEY')
        self.secret_key = os.environ.get('SPACES_SECRET_KEY')
        self.region = os.environ.get('SPACES_REGION', 'sfo3')
        self.bucket_name = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
        
        if not self.access_key or not self.secret_key:
            raise ValueError(
                "SPACES_ACCESS_KEY and SPACES_SECRET_KEY must be set. "
                "Create a Spaces access key in Digital Ocean and add them to environment variables."
            )
        
        # Construct the endpoint URL for Digital Ocean Spaces
        self.endpoint_url = f'https://{self.region}.digitaloceanspaces.com'
        
        # Initialize boto3 S3 client for Digital Ocean Spaces
        self.client = boto3.client(
            's3',
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version='s3v4')
        )
        
        # Public URL base (with CDN if enabled)
        self.public_url_base = f'https://{self.bucket_name}.{self.region}.cdn.digitaloceanspaces.com'
    
    def upload_file(self, file_data, object_name):
        """Upload file to Digital Ocean Spaces"""
        # Determine content type
        content_type = 'application/octet-stream'
        if object_name.endswith('.png'):
            content_type = 'image/png'
        elif object_name.endswith('.jpg') or object_name.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif object_name.endswith('.json'):
            content_type = 'application/json'
        
        # Upload to Spaces
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=object_name,
            Body=file_data,
            ACL='public-read',  # Make publicly accessible
            ContentType=content_type
        )
        
        # Return public URL
        return f'{self.public_url_base}/{object_name}'
    
    def delete_file(self, object_name):
        """Delete file from Digital Ocean Spaces"""
        self.client.delete_object(
            Bucket=self.bucket_name,
            Key=object_name
        )
    
    def get_public_url(self, object_name):
        """Get public URL for an object"""
        return f'{self.public_url_base}/{object_name}'
    
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
    
    def download_file(self, object_name):
        """Download file from Digital Ocean Spaces"""
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            return response['Body'].read()
        except Exception as e:
            print(f"Error downloading {object_name}: {e}")
            return None
    
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


# Helper function for standalone use
def download_from_spaces(object_name):
    """
    Download file from Spaces without needing to instantiate the service class.
    Used by telegram_bot.py and other modules.
    """
    try:
        service = ObjectStorageService()
        return service.download_file(object_name)
    except Exception as e:
        print(f"Error in download_from_spaces: {e}")
        return None
