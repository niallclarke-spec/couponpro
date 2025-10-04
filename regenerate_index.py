#!/usr/bin/env python3
import json
import os
from pathlib import Path

def regenerate_templates_index():
    """Scan templates from object storage (source of truth) and generate index.json"""
    templates = []
    
    # Try to use object storage as source of truth (if available)
    try:
        from object_storage import ObjectStorageService
        import boto3
        from botocore.client import Config
        
        access_key = os.environ.get('SPACES_ACCESS_KEY')
        secret_key = os.environ.get('SPACES_SECRET_KEY')
        region = os.environ.get('SPACES_REGION', 'lon1')
        bucket = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
        
        if access_key and secret_key:
            # Initialize boto3 client
            endpoint = f'https://{region}.digitaloceanspaces.com'
            client = boto3.client('s3', region_name=region, endpoint_url=endpoint,
                                aws_access_key_id=access_key, aws_secret_access_key=secret_key,
                                config=Config(signature_version='s3v4'))
            
            # List all meta.json files from Spaces (source of truth)
            response = client.list_objects_v2(Bucket=bucket, Prefix='templates/')
            meta_files = [obj['Key'] for obj in response.get('Contents', []) 
                         if obj['Key'].endswith('/meta.json') and obj['Key'] != 'templates/index.json']
            
            print(f"[INDEX] Found {len(meta_files)} templates in object storage")
            
            for meta_file in meta_files:
                slug = meta_file.split('/')[1]
                
                # Download meta.json from Spaces
                try:
                    obj = client.get_object(Bucket=bucket, Key=meta_file)
                    meta = json.loads(obj['Body'].read())
                    
                    template_data = {
                        "slug": slug,
                        "name": meta.get("name", slug.replace("-", " ").title()),
                        "meta": f"assets/templates/{slug}/meta.json"
                    }
                    
                    # Extract image URLs from meta
                    if "square" in meta and isinstance(meta["square"], dict):
                        if "imageUrl" in meta["square"]:
                            template_data["square"] = meta["square"]["imageUrl"]
                    
                    if "story" in meta and isinstance(meta["story"], dict):
                        if "imageUrl" in meta["story"]:
                            template_data["story"] = meta["story"]["imageUrl"]
                    
                    # Only include templates that have at least one variant
                    if "square" in template_data or "story" in template_data:
                        templates.append(template_data)
                        print(f"[INDEX] Added template: {slug}")
                    
                except Exception as e:
                    print(f"[INDEX] Warning: Could not read meta.json for {slug}: {e}")
            
            # Sort templates by name
            templates.sort(key=lambda x: x["name"])
            
            # Write index.json locally
            index_data = {"templates": templates}
            index_path = Path("assets/templates/index.json")
            index_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(index_path, 'w') as f:
                json.dump(index_data, f, indent=2)
            
            print(f"[INDEX] Generated index.json with {len(templates)} templates from object storage")
            return index_data
            
    except Exception as e:
        print(f"[INDEX] Could not use object storage: {e}")
        print(f"[INDEX] Falling back to local scan")
    
    # Fallback: scan local directories (for development/legacy)
    templates_dir = Path("assets/templates")
    
    if not templates_dir.exists():
        print("[INDEX] Templates directory does not exist")
        return {"templates": []}
    
    for item in templates_dir.iterdir():
        if item.is_dir() and item.name != "__pycache__":
            slug = item.name
            meta_file = item / "meta.json"
            
            template_data = {
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "meta": f"assets/templates/{slug}/meta.json"
            }
            
            square_img = None
            story_img = None
            
            if meta_file.exists():
                try:
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                        
                        if "name" in meta:
                            template_data["name"] = meta["name"]
                        
                        if "square" in meta and isinstance(meta["square"], dict):
                            if "imageUrl" in meta["square"]:
                                square_img = meta["square"]["imageUrl"]
                        
                        if "story" in meta and isinstance(meta["story"], dict):
                            if "imageUrl" in meta["story"]:
                                story_img = meta["story"]["imageUrl"]
                        
                except Exception as e:
                    print(f"[INDEX] Warning: Could not read meta.json for {slug}: {e}")
            
            if square_img:
                template_data["square"] = square_img
            if story_img:
                template_data["story"] = story_img
            
            if square_img or story_img:
                templates.append(template_data)
            else:
                print(f"[INDEX] Warning: No images found for template '{slug}'")
    
    templates.sort(key=lambda x: x["name"])
    
    index_data = {"templates": templates}
    index_path = templates_dir / "index.json"
    
    with open(index_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    
    print(f"[INDEX] Generated index.json with {len(templates)} templates from local scan")
    return index_data

if __name__ == "__main__":
    result = regenerate_templates_index()
    print(json.dumps(result, indent=2))
