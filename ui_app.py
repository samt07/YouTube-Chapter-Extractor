import streamlit as st
import yt_dlp
import re
import os
import time as time_module
from moviepy import VideoFileClip
import io
import sys

# Page configuration
st.set_page_config(
    page_title="YouTube Chapters Extractor",
    page_icon="🎬",
    layout="wide"
)

def get_video_info(url):
    """Get video title and description from YouTube URL"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': False,
        'nocheckcertificate': True,
        'ignoreerrors': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', ''), info.get('description', ''), info
    except Exception as e:
        st.error(f"Error fetching video info: {e}")
        return "", "", None

def extract_timestamps(description):
    """Extract timestamps from description text - simplified and more robust"""
    timestamps = []
    lines = description.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 4:
            continue
            
        # Simple and direct regex: timestamp at start of line followed by space and text
        # This covers the most common format: "00:00 Title" or "1:23:45 Title"
        match = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', line)
        if match:
            timestamp = match.group(1)
            title = match.group(2).strip()
            
            # Validate timestamp format
            if is_valid_timestamp(timestamp) and len(title) > 1:
                # Clean up title
                title = re.sub(r'^[-–—:\s\[\]()•]+', '', title)
                title = re.sub(r'[,\s\[\]()]+$', '', title)
                
                # Filter out invalid titles
                if not title.startswith('http') and not re.match(r'^\d+$', title):
                    timestamps.append((timestamp, title))
                    continue
        
        # Fallback: Look for timestamps anywhere in the line with various separators
        # This handles: "1:23 - Title", "[1:23] Title", "Title - 1:23", etc.
        timestamp_matches = re.finditer(r'(\d{1,2}:\d{2}(?::\d{2})?)', line)
        for ts_match in timestamp_matches:
            timestamp = ts_match.group(1)
            if not is_valid_timestamp(timestamp):
                continue
                
            ts_start = ts_match.start()
            ts_end = ts_match.end()
            
            title = None
            
            # Look after timestamp for title
            after_text = line[ts_end:].strip()
            if after_text:
                # Remove common separators and get title
                title_match = re.match(r'^[\s\-–—•:\[\]()]*(.+?)(?=\s+\d{1,2}:\d{2}(?::\d{2})?|$)', after_text)
                if title_match:
                    title = title_match.group(1).strip()
            
            # If no title found after, look before timestamp
            if not title and ts_start > 0:
                before_text = line[:ts_start].strip()
                if before_text:
                    # Remove trailing separators and get title
                    title_match = re.search(r'^(.+?)[\s\-–—•:\[\]()]*$', before_text)
                    if title_match:
                        title = title_match.group(1).strip()
            
            # Validate and clean title
            if title and len(title) > 1:
                title = re.sub(r'^[-–—:\s\[\]()•]+', '', title)
                title = re.sub(r'[,\s\[\]()]+$', '', title)
                
                if not title.startswith('http') and not re.match(r'^\d+$', title) and len(title) > 1:
                    timestamps.append((timestamp, title))
    
    # Remove duplicates
    seen = set()
    unique_timestamps = []
    for timestamp, title in timestamps:
        timestamp_seconds = time_to_seconds(timestamp)
        title_key = ' '.join(title.lower().split()[:3])  # First 3 words
        key = (timestamp_seconds, title_key)
        
        if key not in seen:
            seen.add(key)
            unique_timestamps.append((timestamp, title))
    
    # Sort by timestamp
    unique_timestamps.sort(key=lambda x: time_to_seconds(x[0]))
    
    return unique_timestamps

def is_valid_timestamp(timestamp):
    """Validate if a timestamp string is properly formatted"""
    try:
        parts = timestamp.split(':')
        if len(parts) == 2:  # MM:SS
            minutes, seconds = int(parts[0]), int(parts[1])
            return 0 <= minutes <= 999 and 0 <= seconds <= 59
        elif len(parts) == 3:  # HH:MM:SS
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59
        return False
    except (ValueError, IndexError):
        return False

def time_to_seconds(time_str):
    """Convert time string to seconds"""
    try:
        parts = time_str.split(':')
        if len(parts) == 2:  # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:  # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return 0
    except ValueError:
        return 0

def download_video(url, output_path="temp_video", progress_callback=None):
    """Download the YouTube video with real-time progress updates"""
    
    def progress_hook(d):
        if progress_callback and d['status'] == 'downloading':
            # Extract progress information
            if 'downloaded_bytes' in d and 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "Unknown"
                
                # Update progress in UI
                progress_callback(
                    percent, 
                    f"📥 Downloading: {percent:.1f}% at {speed_str}"
                )
            elif 'downloaded_bytes' in d and 'total_bytes_estimate' in d:
                # Use estimate if exact total not available
                percent = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "Unknown"
                
                progress_callback(
                    percent, 
                    f"📥 Downloading: ~{percent:.1f}% at {speed_str}"
                )
    
    ydl_opts = {
        'format': 'best[height<=480]/worst',
        'outtmpl': f'{output_path}.%(ext)s',
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],  # Add progress hook
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Find the downloaded file
        for ext in ['mp4', 'webm', 'mkv', 'avi', 'flv']:
            filepath = f'{output_path}.{ext}'
            if os.path.exists(filepath):
                return filepath
                
        return None
    except Exception as e:
        st.error(f"Download error: {e}")
        return None

def download_video_segment(url, start_time, end_time, output_path="temp_video", progress_callback=None):
    """Download only the specific segment from YouTube video (much faster!)"""
    
    def progress_hook(d):
        if progress_callback and d['status'] == 'downloading':
            # Extract progress information
            if 'downloaded_bytes' in d and 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "Unknown"
                
                # Update progress in UI
                progress_callback(
                    percent, 
                    f"📥 Downloading segment: {percent:.1f}% at {speed_str}"
                )
            elif 'downloaded_bytes' in d and 'total_bytes_estimate' in d:
                # Use estimate if exact total not available
                percent = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "Unknown"
                
                progress_callback(
                    percent, 
                    f"📥 Downloading segment: ~{percent:.1f}% at {speed_str}"
                )
    
    # Convert time to seconds for yt-dlp
    start_seconds = time_to_seconds(start_time)
    end_seconds = time_to_seconds(end_time)
    
    # Use yt-dlp's segment downloading capability
    ydl_opts = {
        'format': 'best[height<=480]/worst',
        'outtmpl': f'{output_path}.%(ext)s',
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        # Download only the specific segment using ffmpeg
        'external_downloader': 'ffmpeg',
        'external_downloader_args': {
            'ffmpeg_i': ['-ss', str(start_seconds), '-to', str(end_seconds)]
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }]
    }
    
    try:
        if progress_callback:
            progress_callback(0, f"🎯 Preparing to download segment ({start_time} - {end_time})...")
        
        # Clear any existing temp files first
        import glob
        for existing_file in glob.glob(f"{output_path}.*"):
            try:
                os.remove(existing_file)
            except:
                pass
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Find the downloaded file more robustly
        for ext in ['mp4', 'webm', 'mkv', 'avi', 'flv']:
            filepath = f'{output_path}.{ext}'
            if os.path.exists(filepath):
                if progress_callback:
                    progress_callback(100, f"✅ Segment downloaded successfully!")
                return filepath
        
        # Also check for any files that start with our output_path
        import glob
        possible_files = glob.glob(f"{output_path}*")
        if possible_files:
            # Return the first match
            if progress_callback:
                progress_callback(100, f"✅ Segment downloaded successfully!")
            return possible_files[0]
                
        return None
    except Exception as e:
        # Fallback to full video download if segment download fails
        if progress_callback:
            progress_callback(0, f"⚠️ Segment download failed ({str(e)}), using full video download...")
        return download_video(url, output_path, progress_callback)

class ProgressCapture:
    """Enhanced capture of MoviePy progress for detailed UI updates"""
    def __init__(self, progress_callback):
        self.progress_callback = progress_callback
        self.current_step = ""
        self.base_progress = 75
        self.current_stage = "init"
        self.audio_start_time = None
        self.video_start_time = None
        
    def write(self, text):
        # Capture MoviePy progress messages
        if self.progress_callback:
            text = text.strip()
            
            # Debug: Show what text we're receiving (uncomment for debugging)
            # if text and len(text) > 5:
            #     print(f"DEBUG MoviePy: {text}")
            
            # Look for audio processing start
            if "writing audio" in text.lower():
                self.current_stage = "audio"
                self.current_step = "Processing audio track"
                self.audio_start_time = time_module.time()
                self.progress_callback(self.base_progress + 1, "🎵 Processing audio track...")
            
            # Look for video processing start  
            elif "writing video" in text.lower():
                self.current_stage = "video"
                self.current_step = "Writing video data"
                self.video_start_time = time_module.time()
                self.progress_callback(self.base_progress + 4, "📹 Writing video data...")
            
            # Look for building stage
            elif "building" in text.lower():
                self.current_stage = "building"
                self.current_step = "Building video structure"
                self.progress_callback(self.base_progress, "🎬 Building video structure...")
            
            # Detect completion messages with progress updates
            elif "done" in text.lower():
                if self.current_stage == "audio":
                    elapsed = time_module.time() - self.audio_start_time if self.audio_start_time else 0
                    self.progress_callback(self.base_progress + 3, f"✅ Audio processing completed ({elapsed:.1f}s)")
                    self.current_stage = "video_prep"
                elif self.current_stage == "video":
                    elapsed = time_module.time() - self.video_start_time if self.video_start_time else 0
                    self.progress_callback(self.base_progress + 10, f"✅ Video processing completed ({elapsed:.1f}s)")
                    self.current_stage = "complete"
            
            # Look for chunk progress (priority over time-based estimation)
            elif ("chunk" in text.lower() and "/" in text) or ("t:" in text and "%" in text):
                try:
                    # Try multiple chunk patterns
                    chunk_patterns = [
                        r'chunk[:\s]*(\d+)/(\d+)',
                        r'(\d+)/(\d+)\s*chunk',
                        r'chunk\s*(\d+)\s*/\s*(\d+)',
                    ]
                    
                    chunk_matched = False
                    for pattern in chunk_patterns:
                        chunk_match = re.search(pattern, text, re.IGNORECASE)
                        if chunk_match:
                            current_chunk = int(chunk_match.group(1))
                            total_chunks = int(chunk_match.group(2))
                            chunk_percent = (current_chunk / total_chunks) * 100
                            
                            if self.current_stage == "audio":
                                ui_progress = self.base_progress + 1 + (chunk_percent / 100) * 2
                                self.progress_callback(ui_progress, f"🎵 Processing audio: chunk {current_chunk}/{total_chunks} ({chunk_percent:.0f}%)")
                            elif self.current_stage == "video":
                                ui_progress = self.base_progress + 4 + (chunk_percent / 100) * 6
                                self.progress_callback(ui_progress, f"📹 Writing video: chunk {current_chunk}/{total_chunks} ({chunk_percent:.0f}%)")
                            else:
                                # General processing
                                ui_progress = self.base_progress + (chunk_percent / 100) * 10
                                self.progress_callback(ui_progress, f"🎬 Processing: chunk {current_chunk}/{total_chunks} ({chunk_percent:.0f}%)")
                            chunk_matched = True
                            break
                    
                    # Also try to extract direct percentage if no chunk found
                    if not chunk_matched and "%" in text:
                        percent_match = re.search(r'(\d+(?:\.\d+)?)%', text)
                        if percent_match:
                            percent = float(percent_match.group(1))
                            if self.current_stage == "audio":
                                ui_progress = self.base_progress + 1 + (percent / 100) * 2
                                self.progress_callback(ui_progress, f"🎵 Processing audio: {percent:.0f}%")
                            elif self.current_stage == "video":
                                ui_progress = self.base_progress + 4 + (percent / 100) * 6
                                self.progress_callback(ui_progress, f"📹 Writing video: {percent:.0f}%")
                except:
                    pass
            
            # Look for frame progress or any progress indicators
            elif ("frame" in text.lower() and ("/" in text or "%" in text)) or (any(char.isdigit() for char in text) and ("%" in text or "/" in text)):
                try:
                    # Try frame patterns first
                    frame_patterns = [
                        r'frame[:\s]*(\d+)/(\d+)',
                        r'(\d+)/(\d+)\s*frame',
                        r'frame\s*(\d+)\s*/\s*(\d+)',
                    ]
                    
                    frame_matched = False
                    for pattern in frame_patterns:
                        frame_match = re.search(pattern, text, re.IGNORECASE)
                        if frame_match:
                            current_frame = int(frame_match.group(1))
                            total_frames = int(frame_match.group(2))
                            frame_percent = (current_frame / total_frames) * 100
                            
                            if self.current_stage == "video":
                                ui_progress = self.base_progress + 4 + (frame_percent / 100) * 6
                                self.progress_callback(ui_progress, f"🎞️ Writing video: frame {current_frame}/{total_frames} ({frame_percent:.0f}%)")
                            else:
                                ui_progress = self.base_progress + (frame_percent / 100) * 10
                                self.progress_callback(ui_progress, f"🎞️ Processing: frame {current_frame}/{total_frames} ({frame_percent:.0f}%)")
                            frame_matched = True
                            break
                    
                    # Try general percentage patterns if no frame pattern matched
                    if not frame_matched and "%" in text:
                        percent_match = re.search(r'(\d+(?:\.\d+)?)%', text)
                        if percent_match:
                            percent = float(percent_match.group(1))
                            if self.current_stage == "video":
                                ui_progress = self.base_progress + 4 + (percent / 100) * 6
                                self.progress_callback(ui_progress, f"🎞️ Writing video: {percent:.0f}%")
                            elif self.current_stage == "audio":
                                ui_progress = self.base_progress + 1 + (percent / 100) * 2
                                self.progress_callback(ui_progress, f"🎵 Processing audio: {percent:.0f}%")
                            else:
                                ui_progress = self.base_progress + (percent / 100) * 10
                                self.progress_callback(ui_progress, f"🎬 Processing: {percent:.0f}%")
                except:
                    pass
            
            # Capture any other progress indicators in real-time
            elif self.current_stage in ["audio", "video"]:
                # Try to extract any numerical progress indicators
                try:
                    # Look for various progress patterns
                    patterns = [
                        r'(\d+(?:\.\d+)?)%',  # Direct percentage
                        r'(\d+)/(\d+)',       # Progress like 5/10
                        r't:\s*(\d+(?:\.\d+)?)s',  # Time elapsed
                        r'(\d+(?:\.\d+)?)fps',     # Frame rate indicator
                    ]
                    
                    progress_found = False
                    
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            if self.current_stage == "audio":
                                # Audio processing: simulate progress over time
                                elapsed = time_module.time() - self.audio_start_time if self.audio_start_time else 0
                                estimated_percent = min(90, elapsed * 15)  # Rough estimate
                                ui_progress = self.base_progress + 1 + (estimated_percent / 100) * 2
                                self.progress_callback(ui_progress, f"🎵 Processing audio track ({estimated_percent:.0f}%)...")
                            elif self.current_stage == "video":
                                # Video processing: simulate progress over time
                                elapsed = time_module.time() - self.video_start_time if self.video_start_time else 0
                                estimated_percent = min(90, elapsed * 8)  # Rough estimate
                                ui_progress = self.base_progress + 4 + (estimated_percent / 100) * 6
                                self.progress_callback(ui_progress, f"📹 Writing video data ({estimated_percent:.0f}%)...")
                            progress_found = True
                            break
                    
                    # If no specific pattern found but we're in a processing stage, 
                    # update based on elapsed time
                    if not progress_found:
                        if self.current_stage == "audio" and self.audio_start_time:
                            elapsed = time_module.time() - self.audio_start_time
                            estimated_percent = min(85, elapsed * 12)
                            ui_progress = self.base_progress + 1 + (estimated_percent / 100) * 2
                            if elapsed > 0.5:  # Only show after half second to avoid spam
                                self.progress_callback(ui_progress, f"🎵 Processing audio track ({estimated_percent:.0f}%)...")
                        elif self.current_stage == "video" and self.video_start_time:
                            elapsed = time_module.time() - self.video_start_time
                            estimated_percent = min(85, elapsed * 6)
                            ui_progress = self.base_progress + 4 + (estimated_percent / 100) * 6
                            if elapsed > 0.5:  # Only show after half second to avoid spam
                                self.progress_callback(ui_progress, f"📹 Writing video data ({estimated_percent:.0f}%)...")
                except:
                    pass
    
    def flush(self):
        pass

def extract_segment_fast(video_path, start_time, end_time, output_filename, progress_callback=None):
    """Extract segment with detailed progress tracking - optimized for pre-segmented videos"""
    video = None
    segment = None
    
    try:
        if progress_callback:
            progress_callback(65, "📼 Loading video segment...")
        
        video = VideoFileClip(video_path)
        
        # If this is already a segment (small file), we might not need to re-extract
        if video.duration <= (time_to_seconds(end_time) - time_to_seconds(start_time)) + 5:
            # Video is already close to segment size, just convert format if needed
            if progress_callback:
                progress_callback(70, "✅ Video is already segmented, converting format...")
            
            # Just copy/convert the file
            if video_path.endswith('.mp4') and output_filename.endswith('.mp4'):
                # Already correct format, just copy
                import shutil
                shutil.copy2(video_path, output_filename)
                if progress_callback:
                    progress_callback(85, "✅ File copied successfully!")
                return True
        
        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time) if end_time else start_seconds + 30
        
        # Validate times
        if end_seconds > video.duration:
            end_seconds = video.duration
        
        if start_seconds >= end_seconds:
            return False
        
        if progress_callback:
            progress_callback(70, "✂️ Creating video segment...")
        
        # Extract segment
        segment = video.subclipped(start_seconds, end_seconds)
        
        if progress_callback:
            progress_callback(75, "🔄 Starting video conversion...")
            
            # Capture MoviePy output for detailed progress
            original_stdout = sys.stdout
            progress_capture = ProgressCapture(progress_callback)
            progress_capture.base_progress = 75
            sys.stdout = progress_capture
        
        try:
            # Simplified codec settings for better compatibility
            segment.write_videofile(output_filename)
        finally:
            if progress_callback:
                sys.stdout = original_stdout
        
        if progress_callback:
            progress_callback(85, "✅ Video segment saved successfully!")
        
        # Verify output file
        return os.path.exists(output_filename)
        
    except Exception as e:
        st.error(f"Extraction error: {e}")
        return False
        
    finally:
        if segment:
            try:
                segment.close()
            except:
                pass
        if video:
            try:
                video.close()
            except:
                pass

def clean_filename(title):
    """Clean title for use as filename - complete description with Windows compatibility"""
    # Remove invalid filename characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', title)
    # Remove URLs and extra spaces
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Remove only the most problematic characters, keep parentheses for music info
    cleaned = re.sub(r'["\'"`,]', '', cleaned)
    # Replace remaining problematic chars with underscores
    cleaned = re.sub(r'[{}[\];]', '_', cleaned)
    # Return complete description (Windows supports up to 255 chars in filename)
    return cleaned

def safe_file_cleanup(file_path):
    """Safely remove file"""
    try:
        if os.path.exists(file_path):
            time_module.sleep(1)
            os.remove(file_path)
    except:
        pass

# Main UI
def main():
    st.title("🎬 YouTube Chapters Extractor")
    st.markdown("Extract video chapters from YouTube videos based on timestamps in descriptions")
    
    # Create output directory
    os.makedirs("extracted_segments", exist_ok=True)
    
    # Initialize session state for timestamps
    if 'timestamps' not in st.session_state:
        st.session_state.timestamps = []
    if 'video_title' not in st.session_state:
        st.session_state.video_title = ""
    if 'current_url' not in st.session_state:
        st.session_state.current_url = ""
    if 'extracted_files' not in st.session_state:
        st.session_state.extracted_files = []
    
    # Input section
    st.header("📋 Input")
    
    # Check if we have analyzed data (disable input if we do)
    has_analyzed_data = bool(st.session_state.timestamps) or bool(st.session_state.video_title)
    
    url = st.text_input(
        "Enter YouTube URL:",
        value=st.session_state.current_url if has_analyzed_data else "",
        placeholder="https://www.youtube.com/watch?v=..." if not has_analyzed_data else "Click Clear to enter a new URL",
        help="Paste the YouTube video URL here" if not has_analyzed_data else "🔒 URL input locked. Click the Clear button to reset and enter a new URL.",
        disabled=has_analyzed_data
    )
    

    
    # Buttons row
    col1, col2 = st.columns([3, 1])
    
    with col1:
        analyze_button = st.button("🔍 Get Chapter info", type="secondary", disabled=has_analyzed_data)
    
    with col2:
        if st.button("🗑️ Clear", type="secondary"):
            # Clear all session state
            st.session_state.timestamps = []
            st.session_state.video_title = ""
            st.session_state.current_url = ""
            st.session_state.extracted_files = []
            st.success("✅ Cleared! Ready for new URL.")
            st.rerun()
    
    # Button to analyze video (separate from extraction)
    if analyze_button:
        if not url.strip():
            st.error("Please enter a YouTube URL")
            return
        
        # Store the URL immediately when analysis starts
        st.session_state.current_url = url
        
        with st.spinner("Analyzing video..."):
            title, description, info = get_video_info(url)
            
            if not title:
                st.error("❌ Could not fetch video information.")
                return
            
            timestamps = extract_timestamps(description)
            
            # Debug: Show first part of description for troubleshooting
            if not timestamps:
                st.warning("⚠️ No timestamps found in video description.")
                with st.expander("🔍 Debug: View Description (First 500 chars)"):
                    st.text(description[:500] if description else "No description found")
                
                # Store the fact that we analyzed but found no timestamps  
                st.session_state.video_title = title
                # URL already stored at start of analyze_button
                # Don't return here - let the app continue to show the full video download section
            
            else:
                # Store in session state
                st.session_state.timestamps = timestamps
                st.session_state.video_title = title
                # URL already stored at start of analyze_button
                
                st.success(f"🎬 **Video:** {title}")
                st.success(f"📊 **Found {len(timestamps)} chapters**")
    
    # Show option for full video download if no timestamps but we have a video title (means analysis was done but no chapters found)
    if st.session_state.video_title and not st.session_state.timestamps:
        st.header("📥 Full Video Download")
        st.info("⚠️ No chapters were found in this video's description.")
        st.info("💡 **Option**: You can download the entire video without chapters.")
        
        # Center the button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            download_complete = st.button("📥 Get Complete Video", type="primary", key="full_video_download_main")
        
        if download_complete:
            # Execute download immediately
            st.header("📥 Processing Complete Video Download")
            
            # Get the current URL from session state
            current_url = st.session_state.current_url
            current_title = st.session_state.video_title
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # Step 1: Video info ready
                status_text.text("🔍 Step 1/6 (5%): Video info ready...")
                progress_bar.progress(5)
                time_module.sleep(0.3)
                
                # Step 2: Full video selected
                status_text.text("📊 Step 2/6 (15%): Full video selected...")
                progress_bar.progress(15)
                time_module.sleep(0.3)
                
                # Step 3: Creating directories
                status_text.text("📁 Step 3/6 (25%): Creating output directory...")
                progress_bar.progress(25)
                os.makedirs("extracted_segments", exist_ok=True)
                time_module.sleep(0.3)
                
                # Step 4: Download entire video
                status_text.text("⬇️ Step 4/6 (45%): Downloading complete video...")
                progress_bar.progress(45)
                time_module.sleep(0.3)
                
                def download_progress_callback_main(percent, message):
                    overall_progress = 45 + (percent / 100) * 40
                    progress_bar.progress(int(overall_progress))
                    status_text.text(f"📥 Step 4/6 ({overall_progress:.0f}%): {message}")
                
                # Download full video
                video_path = download_video(current_url, progress_callback=download_progress_callback_main)
                
                if not video_path:
                    st.error("❌ Failed to download video.")
                    return
                
                file_size = os.path.getsize(video_path) / (1024 * 1024)
                status_text.text("✅ Step 4/6 (85%): Complete video downloaded!")
                progress_bar.progress(85)
                st.success(f"📁 **Complete Video Downloaded:** {file_size:.1f} MB")
                time_module.sleep(0.5)
                
                # Step 5: Save as complete video
                clean_title = clean_filename(current_title if current_title else "Complete_Video")
                output_filename = f"extracted_segments/{clean_title}.mp4"
                
                status_text.text("📋 Step 5/6 (90%): Saving complete video...")
                progress_bar.progress(90)
                
                # Copy the downloaded video to output directory
                import shutil
                shutil.copy2(video_path, output_filename)
                
                status_text.text("✅ Step 5/6 (95%): Complete video saved!")
                progress_bar.progress(95)
                time_module.sleep(0.3)
                
                # Step 6: Cleanup and final result
                status_text.text("🧹 Step 6/6 (100%): Cleaning up...")
                progress_bar.progress(100)
                safe_file_cleanup(video_path)
                
                # Final success message
                st.success("🎉 **Complete video downloaded successfully!**")
                
                # Show download button for the complete video
                if os.path.exists(output_filename):
                    file_size_mb = os.path.getsize(output_filename) / (1024 * 1024)
                    
                    with open(output_filename, "rb") as file:
                        st.download_button(
                            label=f"📥 Download Video ({file_size_mb:.1f} MB)",
                            data=file.read(),
                            file_name=os.path.basename(output_filename),
                            mime="video/mp4",
                            type="primary"
                        )
                
            except Exception as e:
                st.error(f"❌ Error downloading complete video: {e}")
                status_text.text("❌ Download failed!")
                progress_bar.progress(0)
    
    # Show chapter selection if timestamps are available
    if st.session_state.timestamps:
        st.header("📝 Chapter Selection")
        
        # Create options for dropdown
        chapter_options = ["🎯 First Chapter Only", "📚 All Chapters"]
        for i, (time, desc) in enumerate(st.session_state.timestamps, 1):
            chapter_options.append(f"{time} - {desc}")
        
        selected_option = st.selectbox(
            "Choose a chapter to extract:",
            chapter_options,
            help="Select from the list of chapters"
        )
        
        if st.button("🚀 Extract selected chapter", type="primary"):
            # Use stored URL from session state if available, otherwise use input URL
            current_url = st.session_state.current_url if st.session_state.current_url else url
            if not current_url.strip():
                st.error("Please enter a YouTube URL")
                return
            
            # Determine which chapters to extract
            if selected_option == "🎯 First Chapter Only":
                chapters_to_extract = [st.session_state.timestamps[0]]
            elif selected_option == "📚 All Chapters":
                chapters_to_extract = st.session_state.timestamps
            else:
                # Extract specific chapter - find by timestamp
                selected_timestamp = selected_option.split(" - ")[0]  # Get timestamp part
                chapters_to_extract = [ts for ts in st.session_state.timestamps if ts[0] == selected_timestamp]
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # Step 1: Get video info (quick since already done)
                status_text.text("✅ Step 1/6 (15%): Using cached video information...")
                progress_bar.progress(15)
                time_module.sleep(0.3)
                
                # Step 2: Already have timestamps
                status_text.text("✅ Step 2/6 (30%): Using extracted chapters...")
                progress_bar.progress(30)
                time_module.sleep(0.3)
                
                # Step 3: Process chapters
                status_text.text(f"🎯 Step 3/6 (40%): Processing {len(chapters_to_extract)} chapter(s)...")
                progress_bar.progress(40)
                time_module.sleep(0.3)
                
                # Step 4: Download video segment (FASTER!)
                status_text.text("⬇️ Step 4/6 (45%): Initiating optimized segment download...")
                progress_bar.progress(45)
                time_module.sleep(0.3)
                
                # Create progress callback for download
                def download_progress_callback(percent, message):
                    # Map download progress to overall progress (45% to 60%)
                    overall_progress = 45 + (percent / 100) * 15  # 15% range for download
                    progress_bar.progress(int(overall_progress))
                    status_text.text(f"📥 Step 4/6 ({overall_progress:.0f}%): {message}")
                
                # Use segment-only download for first chapter, full video for multiple chapters
                if len(chapters_to_extract) == 1:
                    start_time = chapters_to_extract[0][0]
                    # Calculate end time for the chapter
                    chapter_index = st.session_state.timestamps.index(chapters_to_extract[0])
                    if chapter_index + 1 < len(st.session_state.timestamps):
                        end_time = st.session_state.timestamps[chapter_index + 1][0]
                    else:
                        start_seconds = time_to_seconds(start_time)
                        end_seconds = start_seconds + 60  # Default 1 minute
                        end_time = f"{end_seconds//60}:{end_seconds%60:02d}"
                    
                    video_path = download_video_segment(current_url, start_time, end_time, progress_callback=download_progress_callback)
                else:
                    video_path = download_video(current_url, progress_callback=download_progress_callback)
                
                if not video_path:
                    st.error("❌ Failed to download video.")
                    return
                
                file_size = os.path.getsize(video_path) / (1024 * 1024)
                status_text.text("✅ Step 4/6 (60%): Video download completed!")
                progress_bar.progress(60)
                st.success(f"📁 **Video Downloaded:** {file_size:.1f} MB")
                time_module.sleep(0.3)
                
                # Step 5: Extract chapters
                extracted_files = []
                total_chapters = len(chapters_to_extract)
                
                for i, (start_time, segment_title) in enumerate(chapters_to_extract):
                    # Calculate end time
                    chapter_index = st.session_state.timestamps.index((start_time, segment_title))
                    if chapter_index + 1 < len(st.session_state.timestamps):
                        end_time = st.session_state.timestamps[chapter_index + 1][0]
                    else:
                        start_seconds = time_to_seconds(start_time)
                        end_seconds = start_seconds + 60  # Default 1 minute for last chapter
                        end_time = f"{end_seconds//60}:{end_seconds%60:02d}"
                    
                    clean_title = clean_filename(segment_title)  
                    output_filename = f"extracted_segments/{i+1:02d}_{clean_title}.mp4"
                    
                    # Create progress callback for extraction
                    def extraction_progress_callback(percent, message):
                        # Map extraction progress considering multiple chapters
                        base_progress = 60 + (i / total_chapters) * 25  # 25% range for all extractions
                        chapter_progress = max(0, (percent - 65) / 20) * (25 / total_chapters)  # Individual chapter progress
                        total_progress = base_progress + chapter_progress
                        progress_bar.progress(int(min(total_progress, 85)))
                        status_text.text(f"🎬 Step 5/6 ({total_progress:.0f}%): Chapter {i+1}/{total_chapters} - {message}")
                    
                    # Use the optimized extraction function
                    success = extract_segment_fast(video_path, start_time, end_time, output_filename, extraction_progress_callback)
                    
                    if success:
                        extracted_files.append(output_filename)
                        # Also store in session state for persistence
                        if output_filename not in st.session_state.extracted_files:
                            st.session_state.extracted_files.append(output_filename)
                        st.success(f"✅ Chapter {i+1}/{total_chapters} extracted: {segment_title}")
                    else:
                        st.error(f"❌ Failed to extract chapter {i+1}: {segment_title}")
                
                # Step 6: Cleanup
                status_text.text("🧹 Step 6/6 (90%): Cleaning up temporary files...")
                progress_bar.progress(90)
                safe_file_cleanup(video_path)
                time_module.sleep(0.3)
                
                status_text.text("✅ Step 6/6 (95%): Cleanup completed!")
                progress_bar.progress(95)
                
                if extracted_files:
                    progress_bar.progress(100)
                    status_text.text(f"🎉 Chapter extraction completed successfully! (100%) - {len(extracted_files)} files created")
                    
                    # Show results
                    st.success(f"🎉 **SUCCESS! {len(extracted_files)} chapter(s) extracted!**")
                            
                else:
                    st.error("❌ No chapters were extracted successfully.")
                    
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                progress_bar.progress(0)
                status_text.text("❌ Process failed")
    
    # Persistent Results Section - Show all extracted files from session state
    if st.session_state.extracted_files:
        st.header("📁 Extracted Files")
        st.markdown("*Download any of your extracted chapters:*")
        
        for i, filename in enumerate(st.session_state.extracted_files):
            if os.path.exists(filename):
                file_size = os.path.getsize(filename) / (1024 * 1024)
                
                # Extract chapter info from filename
                basename = os.path.basename(filename)
                # Remove the .mp4 extension and extract chapter number and title
                chapter_name = basename.replace('.mp4', '')
                if '_' in chapter_name and chapter_name[:2].isdigit():
                    chapter_num = chapter_name[:2]
                    chapter_title = chapter_name[3:]  # Skip the number and underscore
                else:
                    chapter_num = str(i+1)
                    chapter_title = chapter_name
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**Chapter {chapter_num}:** {chapter_title}")
                    st.write(f"📍 `{filename}`")
                
                with col2:
                    st.metric("Size", f"{file_size:.1f} MB")
                
                with col3:
                    with open(filename, 'rb') as file:
                        st.download_button(
                            label=f"💾 Download",
                            data=file,
                            file_name=os.path.basename(filename),
                            mime="video/mp4",
                            key=f"persistent_download_{i}"
                        )
                
                st.divider()

if __name__ == "__main__":
    main() 