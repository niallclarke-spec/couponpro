#!/usr/bin/env python3
import json
import os
from pathlib import Path

def find_pngs_recursive(folder):
    """Find all PNG files recursively in a folder"""
    pngs = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith('.png'):
                full_path = os.path.join(root, file)
                pngs.append(str(Path(full_path).relative_to(".")))
    return pngs

def regenerate_templates_index():
    """Scan assets/templates and generate index.json"""
    templates_dir = Path("assets/templates")
    templates = []
    
    if not templates_dir.exists():
        print("Templates directory does not exist")
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
                        
                        if "square" in meta:
                            square_val = meta["square"]
                            if isinstance(square_val, str):
                                check_path = square_val.lstrip('/')
                                if os.path.exists(check_path):
                                    square_img = check_path
                            elif isinstance(square_val, dict):
                                # Check for imageUrl first (object storage), then image (legacy)
                                if "imageUrl" in square_val:
                                    square_img = square_val["imageUrl"]
                                elif "image" in square_val:
                                    check_path = square_val["image"].lstrip('/')
                                    if os.path.exists(check_path):
                                        square_img = check_path
                        
                        if "story" in meta:
                            story_val = meta["story"]
                            if isinstance(story_val, str):
                                check_path = story_val.lstrip('/')
                                if os.path.exists(check_path):
                                    story_img = check_path
                            elif isinstance(story_val, dict):
                                # Check for imageUrl first (object storage), then image (legacy)
                                if "imageUrl" in story_val:
                                    story_img = story_val["imageUrl"]
                                elif "image" in story_val:
                                    check_path = story_val["image"].lstrip('/')
                                    if os.path.exists(check_path):
                                        story_img = check_path
                except Exception as e:
                    print(f"Warning: Could not read meta.json for {slug}: {e}")
            
            if not square_img or not story_img:
                pngs = find_pngs_recursive(str(item))
                
                if not square_img:
                    square_img = next((p for p in pngs if "square" in p.lower()), None)
                if not story_img:
                    story_img = next((p for p in pngs if "story" in p.lower()), None)
                
                if not square_img and pngs:
                    square_img = pngs[0]
                if not story_img and len(pngs) > 1:
                    story_img = pngs[1]
                elif not story_img and pngs:
                    story_img = pngs[0]
            
            if square_img:
                template_data["square"] = square_img
            if story_img:
                template_data["story"] = story_img
            
            if square_img or story_img:
                templates.append(template_data)
            else:
                print(f"Warning: No images found for template '{slug}'")
    
    templates.sort(key=lambda x: x["name"])
    
    index_data = {"templates": templates}
    index_path = templates_dir / "index.json"
    
    with open(index_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    
    print(f"Generated index.json with {len(templates)} templates")
    return index_data

if __name__ == "__main__":
    result = regenerate_templates_index()
    print(json.dumps(result, indent=2))
