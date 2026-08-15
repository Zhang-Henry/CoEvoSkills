import requests
from bs4 import BeautifulSoup
import asyncio
import edge_tts
import subprocess
import os
import re
import tempfile


def fetch_essay_text(url, timeout=30):
    """Fetch a Paul Graham essay and extract the main text content."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Remove script and style elements
    for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    
    # Get text preserving paragraph structure
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up: remove excessive whitespace and blank lines
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Remove footnote references like [1], [2] etc.
    text = re.sub(r'\[\d+\]', '', text)
    
    return text


def clean_essay_text(raw_text, essay_title=None):
    """Clean essay text by removing navigation chrome, headers, footers.
    Tries to isolate just the essay content."""
    lines = raw_text.split('\n')
    
    # Find the essay start - look for the title or first substantial paragraph
    start_idx = 0
    if essay_title:
        for i, line in enumerate(lines):
            if essay_title.lower() in line.lower():
                start_idx = i
                break
    
    # Remove common PG site chrome at the end
    end_idx = len(lines)
    chrome_markers = ['Thanks to', 'Related:', 'If you liked', 'Want to start a startup?']
    
    # Keep 'Thanks to' as it's part of the essay
    # Just remove navigation links at the very end
    for i in range(len(lines) - 1, max(len(lines) - 10, 0), -1):
        line = lines[i].strip()
        if any(marker in line for marker in ['Japanese Translation', 'Chinese Translation', 'Russian Translation', 'Korean Translation']):
            end_idx = i
    
    cleaned = '\n'.join(lines[start_idx:end_idx])
    return cleaned.strip()


def chunk_text(text, max_chars=4000):
    """Split text into chunks at sentence boundaries, respecting max char limit.
    Edge-tts can handle reasonably long text but we chunk for reliability."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


async def _tts_chunk(text, output_path, voice='en-US-AriaNeural', retries=3):
    """Convert a text chunk to speech using edge-tts with retries."""
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            # Verify the file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception as e:
            print(f"TTS attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
    return False


async def text_to_speech_chunks(text_chunks, output_dir, voice='en-US-AriaNeural'):
    """Convert list of text chunks to individual mp3 files.
    Returns list of output file paths in order."""
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    
    for i, chunk in enumerate(text_chunks):
        output_path = os.path.join(output_dir, f'chunk_{i:04d}.mp3')
        print(f"Converting chunk {i+1}/{len(text_chunks)} ({len(chunk)} chars)...")
        success = await _tts_chunk(chunk, output_path, voice)
        if success:
            output_files.append(output_path)
        else:
            print(f"WARNING: Failed to convert chunk {i+1}")
    
    return output_files


def concatenate_audio_files(file_list, output_path):
    """Concatenate mp3 files using ffmpeg concat demuxer."""
    if not file_list:
        raise ValueError("No audio files to concatenate")
    
    # Create a concat list file
    list_file = output_path + '.list.txt'
    with open(list_file, 'w') as f:
        for fpath in file_list:
            # Escape single quotes in path
            escaped = fpath.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    
    # Use ffmpeg to concatenate
    cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
        '-i', list_file,
        '-c:a', 'libmp3lame', '-q:a', '2',
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"ffmpeg stderr: {result.stderr}")
        raise RuntimeError(f"ffmpeg concatenation failed: {result.returncode}")
    
    # Clean up list file
    os.remove(list_file)
    
    return output_path


def validate_audio(file_path, min_duration_seconds=10):
    """Validate the output audio file has nontrivial duration."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Output file not found: {file_path}")
    
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"Output file is empty: {file_path}")
    
    # Use ffprobe to check duration
    cmd = [
        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {file_path}")
    
    duration = float(result.stdout.strip())
    print(f"Audio duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    
    if duration < min_duration_seconds:
        raise ValueError(f"Audio too short: {duration}s < {min_duration_seconds}s minimum")
    
    return duration


def run_pipeline(essays, output_path, voice='en-US-AriaNeural'):
    """End-to-end pipeline: fetch essays, convert to speech, concatenate.
    
    Args:
        essays: list of dicts with 'url' and 'title' keys
        output_path: path for the final mp3 file
        voice: edge-tts voice name
    """
    all_chunk_files = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, essay in enumerate(essays):
            print(f"\n=== Processing essay {idx+1}: {essay['title']} ===")
            
            # Fetch and clean
            raw_text = fetch_essay_text(essay['url'])
            cleaned_text = clean_essay_text(raw_text, essay['title'])
            print(f"Extracted {len(cleaned_text)} chars of text")
            
            # Chunk
            chunks = chunk_text(cleaned_text)
            print(f"Split into {len(chunks)} chunks")
            
            # TTS
            essay_dir = os.path.join(tmpdir, f'essay_{idx}')
            chunk_files = asyncio.run(
                text_to_speech_chunks(chunks, essay_dir, voice)
            )
            all_chunk_files.extend(chunk_files)
            print(f"Generated {len(chunk_files)} audio chunks")
        
        # Concatenate all
        print(f"\n=== Concatenating {len(all_chunk_files)} total chunks ===")
        concatenate_audio_files(all_chunk_files, output_path)
    
    # Validate
    duration = validate_audio(output_path)
    print(f"\nSuccess! Audiobook saved to {output_path} ({duration/60:.1f} minutes)")
    return output_path
