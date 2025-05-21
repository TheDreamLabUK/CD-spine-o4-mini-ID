# app.py
import os
import json
import requests
import musicbrainzngs
from PIL import Image
import pytesseract

# --- OCR & API Clients will be configured after user input ---

def extract_text(image_file, openai_client=None) -> list:
    """
    Extract text lines from image using OpenAI o4-mini if a client provided, else pytesseract.
    """
    if openai_client:
        response = openai_client.ChatCompletion.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": "You are an OCR engine. Extract all text from the provided image, listing one line per entry."},
                {"role": "user",   "content": "Identify and list each distinct line of text on this image."}
            ],
            files=[{"file": image_file, "purpose": "image"}]
        )
        text = response.choices[0].message.content
    else:
        img = Image.open(image_file)
        text = pytesseract.image_to_string(img)
    return [line.strip() for line in text.splitlines() if line.strip()]

def lookup_metadata(lines: list, spotify_client=None) -> list:
    """
    Given text lines, search MusicBrainz and Spotify and return metadata entries.
    """
    musicbrainzngs.set_useragent("CDIdentifierApp", "1.0", "https://example.com")
    results = []
    for query in lines:
        entry = {"query_text": query, "matches": []}
        # MusicBrainz lookup
        try:
            mb = musicbrainzngs.search_releases(query=query, limit=1)
            release_list = mb.get('release-list', [])
            if release_list:
                r = release_list[0]
                mbid = r.get('id')
                artist = r['artist-credit'][0]['artist']['name']
                title = r.get('title')
                cover_url = None
                art_resp = requests.get(f"https://coverartarchive.org/release/{mbid}")
                art_json = art_resp.json()
                if art_json.get('images'):
                    cover_url = art_json['images'][0].get('image')
                entry['matches'].append({
                    'source': 'MusicBrainz',
                    'artist': artist,
                    'title': title,
                    'mbid': mbid,
                    'cover_art_url': cover_url
                })
        except Exception:
            pass
        # Spotify lookup
        if spotify_client:
            try:
                sp_res = spotify_client.search(q=query, type='album', limit=1)
                items = sp_res.get('albums', {}).get('items', [])
                if items:
                    alb = items[0]
                    artist = alb['artists'][0]['name']
                    title = alb['name']
                    cover_url = alb['images'][0]['url'] if alb['images'] else None
                    spotify_id = alb['id']
                    entry['matches'].append({
                        'source': 'Spotify',
                        'artist': artist,
                        'title': title,
                        'spotify_id': spotify_id,
                        'cover_art_url': cover_url
                    })
            except Exception:
                pass
        results.append(entry)
    return results

def main():
    try:
        import streamlit as st
        from spotipy.oauth2 import SpotifyClientCredentials
        import openai
        import spotipy
    except ModuleNotFoundError as e:
        print(f"Error: required package not installed: {e.name}. Run `pip install streamlit spotipy openai`.")
        return

    st.set_page_config(page_title="CD Identifier", layout="centered")
    st.title("CD Identifier and Metadata Fetcher")
    st.sidebar.header("API Credentials")
    openai_key = st.sidebar.text_input("OpenAI API Key", type="password")
    spotify_client_id = st.sidebar.text_input("Spotify Client ID", type="password")
    spotify_client_secret = st.sidebar.text_input("Spotify Client Secret", type="password")

    openai_client = None
    if openai_key:
        openai.api_key = openai_key
        openai_client = openai
    spotify_client = None
    if spotify_client_id and spotify_client_secret:
        creds = SpotifyClientCredentials(client_id=spotify_client_id,
                                         client_secret=spotify_client_secret)
        spotify_client = spotipy.Spotify(client_credentials_manager=creds)

    st.write("Upload an image of CD spines; OCR + metadata lookup will run.")
    uploaded = st.file_uploader("Upload image", type=["jpg", "jpeg", "png"])
    if not uploaded:
        st.info("Awaiting upload...")
        return

    st.image(Image.open(uploaded), use_column_width=True)
    st.write("Extracting text...")
    lines = extract_text(uploaded, openai_client)
    st.subheader("Extracted Text")
    st.write("\n".join(lines))

    st.write("Looking up metadata...")
    results = lookup_metadata(lines, spotify_client)

    st.subheader("Metadata (JSON)")
    st.json(results)

    st.subheader("Metadata (Markdown)")
    md = []
    for entry in results:
        for m in entry['matches']:
            md.append(f"### [{m['source']}] {m.get('artist','')} - {m.get('title','')}")
            if m.get('cover_art_url'):
                md.append(f"![Cover Art]({m['cover_art_url']})")
            if m['source']=='MusicBrainz':
                md.append(f"- **MBID:** {m.get('mbid')}  ")
            if m['source']=='Spotify':
                md.append(f"- **Spotify ID:** {m.get('spotify_id')}  \n")
            md.append(f"- **Query:** {entry['query_text']}  \n")
    st.markdown("\n".join(md))

    json_data = json.dumps(results, indent=2).encode('utf-8')
    st.download_button("Download JSON", json_data, "cd_metadata.json", "application/json")

if __name__ == "__main__":
    main()

