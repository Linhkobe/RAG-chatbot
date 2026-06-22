import os
import sys
import time
from google import genai
from google.genai import types
import yt_dlp
import pygame

def search_and_play_youtube(search_query: str) -> str:
    """
    Searches YouTube, downloads just the audio file temporarily, and plays it.
    """
    print(f"\n🔍 Searching YouTube for: '{search_query}'...")
    
    # A generic filename for our temporary audio
    temp_filename = "temp_song"
    temp_file_with_ext = f"{temp_filename}.mp3"
    
    # Clean up any leftover file from a previous crash
    if os.path.exists(temp_file_with_ext):
        os.remove(temp_file_with_ext)
        
    # Configure yt-dlp to download ONLY the audio directly as an MP3
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch1',
        'outtmpl': f"{temp_filename}.%(ext)s",  
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info and download the audio clip
            info = ydl.extract_info(search_query, download=True)
            video_title = info['entries'][0]['title']
            
            print(f"🎵 Now Playing: {video_title}")
            print("🔊 (Press Ctrl+C in the terminal to stop the music)\n")
            
            # Initialize pygame's audio mixer (completely self-contained inside Python)
            pygame.mixer.init()
            pygame.mixer.music.load(temp_file_with_ext)
            pygame.mixer.music.play()
            
            # Keep script alive while music is playing
            while pygame.mixer.music.get_busy():
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nStopping music player...")
    except Exception as e:
        print(f"Error executing play: {str(e)}")
    finally:
        # UNIVERSAL CLEANUP: Stop the mixer and delete the file so it doesn't waste space
        pygame.mixer.quit()
        if os.path.exists(temp_file_with_ext):
            try:
                os.remove(temp_file_with_ext)
            except Exception:
                pass
        return "Playback finished."

# --- Gemini Client Setup ---
client = genai.Client()

print("🎧 Universal Music Agent Active. What would you like to hear?")
user_prompt = input("You: ")

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=user_prompt,
    config=types.GenerateContentConfig(
        tools=[search_and_play_youtube],
        temperature=0.0,
    )
)

if response.function_calls:
    for function_call in response.function_calls:
        if function_call.name == "search_and_play_youtube":
            search_and_play_youtube(search_query=function_call.args["search_query"])
else:
    print(f"\n🤖 Gemini: {response.text}")