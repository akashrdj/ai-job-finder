#!/usr/bin/env python3
"""
inject_profile.py
=================
Reads your filled-in `my_profile.json` and pushes it to the running backend
so all job matching, resume tailoring, and cover letter generation use YOUR
real details.

Usage:
  1. Fill in my_profile.json with your real details
  2. Make sure the backend is running (uvicorn) on port 8000
  3. Run:  python inject_profile.py

Optional flag:
  python inject_profile.py --port 9000   (if your backend runs on a different port)
"""

import json
import sys
import argparse
from pathlib import Path

try:
    import httpx
except ImportError:
    print("❌  httpx not installed. Run:  pip install httpx")
    sys.exit(1)


def load_profile(profile_path: Path) -> dict:
    """Load and validate my_profile.json, stripping internal comment keys."""
    with open(profile_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Remove comment fields (keys starting with _)
    cleaned = {k: v for k, v in raw.items() if not k.startswith("_")}

    # Basic validation
    required_fields = ["full_name", "email", "skills", "education"]
    missing = [field for field in required_fields if not cleaned.get(field)]
    if missing:
        print(f"⚠️  Warning: These required fields are still empty: {missing}")
        print("   Fill them in my_profile.json before injecting.\n")

    placeholder_check = ["YOUR FULL NAME", "your.email@gmail.com", "+91 XXXXXXXXXX"]
    for ph in placeholder_check:
        if ph in json.dumps(cleaned):
            print(f"⚠️  Warning: Placeholder '{ph}' still found in profile.")
            print("   Replace all placeholders in my_profile.json with your real details.\n")
            break

    return cleaned


def inject_profile(profile: dict, base_url: str) -> None:
    endpoint = f"{base_url}/api/profile"
    print(f"📤  Sending profile to {endpoint} ...")

    response = httpx.post(
        endpoint,
        json=profile,
        headers={"Content-Type": "application/json"},
        timeout=30.0
    )

    if response.status_code == 200:
        saved = response.json()
        print(f"\n✅  Profile saved successfully!")
        print(f"   Name    : {saved.get('full_name')}")
        print(f"   Email   : {saved.get('email')}")
        print(f"   Skills  : {', '.join((saved.get('skills') or [])[:8])}...")
        print(f"   Location: {saved.get('location')}")
        print(f"\n🚀  Go to http://localhost:5173 → 'My Profile & 4 Matrix Variants' tab to verify.")
    else:
        print(f"\n❌  Failed to save profile. Status: {response.status_code}")
        print(f"   Response: {response.text}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Inject my_profile.json into AI Job Finder backend")
    parser.add_argument("--port", type=int, default=8000, help="Backend port (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Backend host (default: 127.0.0.1)")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    profile_path = Path(__file__).parent / "my_profile.json"
    if not profile_path.exists():
        example_path = Path(__file__).parent / "my_profile.example.json"
        print(f"❌  my_profile.json not found at {profile_path}")
        if example_path.exists():
            print(f"💡  Tip: Copy {example_path.name} to my_profile.json and update it with your real details.")
        sys.exit(1)

    print(f"📂  Loading profile from: {profile_path}")
    profile = load_profile(profile_path)

    print(f"👤  Loaded profile for: {profile.get('full_name', 'Unknown')}")
    print(f"   Email   : {profile.get('email')}")
    print(f"   Location: {profile.get('location')}")
    print(f"   Skills  : {len(profile.get('skills', []))} listed")
    print(f"   Projects: {len(profile.get('projects', []))}")
    print(f"   Work Exp: {len(profile.get('work_history', []))} role(s)\n")

    inject_profile(profile, base_url)


if __name__ == "__main__":
    main()
