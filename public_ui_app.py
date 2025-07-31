import streamlit as st
import yt_dlp
import re
import os
import time as time_module
from moviepy import VideoFileClip
import io
import sys
import tempfile
import shutil
import uuid
import atexit
from pathlib import Path
import threading

# ============================================================================
# PUBLIC DEPLOYMENT CONFIGURATION
# ============================================================================

# Resource limits for public deployment
MAX_VIDEO_DURATION = 3600  # 1 hour max
MAX_FILE_SIZE_MB = 500  # 500MB max file size
MAX_CHAPTERS = 20  # Maximum chapters to extract
CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes
TEMP_DIR_RETENTION = 1800  # Keep temp dirs for 30 minutes

# Page configuration
st.set_page_config(
    page_title="YouTube Chapters Extractor",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# SESSION-BASED USER ISOLATION
# ============================================================================

def get_user_session_id():
    """Generate unique session ID for user isolation"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    return st.session_state.session_id

def get_user_temp_dir():
    """Get user-specific temporary directory"""
    session_id = get_user_session_id()
    temp_dir = Path(tempfile.gettempdir()) / "youtube_extractor" / session_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)

def get_user_output_dir():
    """Get user-specific output directory"""
    session_id = get_user_session_id()
    output_dir = Path(get_user_temp_dir()) / "extracted_segments"
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir)

# ============================================================================
# ENHANCED RESOURCE MONITORING
# ============================================================================

def check_system_resources():
    """Check if system has enough resources"""
    try:
        # Check available disk space (need at least 1GB)
        disk_usage = shutil.disk_usage(tempfile.gettempdir())
        free_gb = disk_usage.free / (1024**3)
        
        if free_gb < 1:
            st.error("⚠️ Insufficient disk space. Please try again later.")
            return False
        
        return True
    except:
        return True  # Assume OK if can't check

# ============================================================================
# ENHANCED VIDEO INFO VALIDATION
# ============================================================================

def get_video_info_safe(url):
    """Get video info with enhanced validation and limits"""
    if not url or not isinstance(url, str):
        return "", "", None
    
    # Validate YouTube URL
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
    ]
    
    if not any(re.search(pattern, url) for pattern in youtube_patterns):
        st.error("❌ Please enter a valid YouTube URL")
        return "", "", None
    
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': False,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'socket_timeout': 30,  # 30 second timeout
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', '')
            description = info.get('description', '')
            duration = info.get('duration', 0)
            
            # Check video duration limit
            if duration and duration > MAX_VIDEO_DURATION:
                st.error(f"❌ Video too long ({duration//60} minutes). Maximum allowed: {MAX_VIDEO_DURATION//60} minutes.")
                return "", "", None
            
            # Check if video is available
            if info.get('is_live'):
                st.error("❌ Live streams are not supported.")
                return "", "", None
                
            return title, description, info
            
    except Exception as e:
        error_msg = str(e).lower()
        if 'private' in error_msg:
            st.error("❌ This video is private and cannot be processed.")
        elif 'unavailable' in error_msg:
            st.error("❌ This video is unavailable.")
        elif 'timeout' in error_msg:
            st.error("❌ Request timed out. Please try again.")
        else:
            st.error(f"❌ Error fetching video info: {e}")
        return "", "", None

# ============================================================================
# OPTIMIZED EXTRACTION FUNCTIONS
# ============================================================================

def extract_timestamps(description):
    """Extract timestamps with limits for public deployment"""
    if not description or len(description) > 50000:  # Limit description size
        return []
        
    timestamps = []
    lines = description.split('\n')[:200]  # Limit lines to process
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 4:
            continue
            
        # Simple and direct regex: timestamp at start of line followed by space and text
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
                    
                    # Limit number of chapters for public deployment
                    if len(timestamps) >= MAX_CHAPTERS:
                        break
                    continue
        
        # Fallback: Look for timestamps anywhere in the line with various separators
        timestamp_matches = re.finditer(r'(\d{1,2}:\d{2}(?::\d{2})?)', line)
        for ts_match in timestamp_matches:
            if len(timestamps) >= MAX_CHAPTERS:
                break
                
            timestamp = ts_match.group(1)
            if not is_valid_timestamp(timestamp):
                continue
                
            ts_start = ts_match.start()
            ts_end = ts_match.end()
            
            title = None
            
            # Look after timestamp for title
            after_text = line[ts_end:].strip()
            if after_text:
                title_match = re.match(r'^[\s\-–—•:\[\]()]*(.+?)(?=\s+\d{1,2}:\d{2}(?::\d{2})?|$)', after_text)
                if title_match:
                    title = title_match.group(1).strip()
            
            # If no title found after, look before timestamp
            if not title and ts_start > 0:
                before_text = line[:ts_start].strip()
                if before_text:
                    title_match = re.search(r'^(.+?)[\s\-–—•:\[\]()]*$', before_text)
                    if title_match:
                        title = title_match.group(1).strip()
            
            # Validate and clean title
            if title and len(title) > 1:
                title = re.sub(r'^[-–—:\s\[\]()•]+', '', title)
                title = re.sub(r'[,\s\[\]()]+$', '', title)
                
                if not title.startswith('http') and not re.match(r'^\d+$', title) and len(title) > 1:
                    timestamps.append((timestamp, title))
    
    # Remove duplicates and sort
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
    
    return unique_timestamps[:MAX_CHAPTERS]  # Enforce limit

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

# ============================================================================
# ENHANCED DOWNLOAD FUNCTIONS WITH LIMITS
# ============================================================================

def download_video_safe(url, progress_callback=None):
    """Download video with safety limits"""
    if not check_system_resources():
        return None
        
    temp_dir = get_user_temp_dir()
    output_path = os.path.join(temp_dir, f"temp_video_{int(time_module.time())}")
    
    def progress_hook(d):
        if progress_callback and d['status'] == 'downloading':
            if 'downloaded_bytes' in d:
                downloaded_mb = d['downloaded_bytes'] / (1024 * 1024)
                
                # Check file size limit
                if downloaded_mb > MAX_FILE_SIZE_MB:
                    raise Exception(f"File too large (>{MAX_FILE_SIZE_MB}MB)")
                
                if 'total_bytes' in d:
                    percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    speed = d.get('speed', 0)
                    speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "Unknown"
                    
                    progress_callback(
                        percent, 
                        f"📥 Downloading: {percent:.1f}% ({downloaded_mb:.1f}MB) at {speed_str}"
                    )
    
    ydl_opts = {
        'format': 'best[height<=720]/best[height<=480]/worst',  # Limit to 720p max
        'outtmpl': f'{output_path}.%(ext)s',
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        'socket_timeout': 60,
        'retries': 2,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Find the downloaded file
        for ext in ['mp4', 'webm', 'mkv', 'avi', 'flv']:
            filepath = f'{output_path}.{ext}'
            if os.path.exists(filepath):
                # Check final file size
                file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if file_size_mb > MAX_FILE_SIZE_MB:
                    os.remove(filepath)
                    st.error(f"❌ File too large ({file_size_mb:.1f}MB). Maximum allowed: {MAX_FILE_SIZE_MB}MB")
                    return None
                return filepath
                
        return None
    except Exception as e:
        error_msg = str(e)
        if "File too large" in error_msg:
            st.error(f"❌ {error_msg}")
        else:
            st.error(f"❌ Download error: {e}")
        return None

# ============================================================================
# ENHANCED EXTRACTION WITH RESOURCE MANAGEMENT
# ============================================================================

def extract_segment_safe(video_path, start_time, end_time, output_filename, progress_callback=None):
    """Extract segment with enhanced safety and resource management"""
    video = None
    segment = None
    
    try:
        if progress_callback:
            progress_callback(65, "📼 Loading video segment...")
        
        # Check input file size
        if os.path.exists(video_path):
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                st.error(f"❌ Input file too large ({file_size_mb:.1f}MB)")
                return False
        
        video = VideoFileClip(video_path)
        
        # Validate video duration
        if video.duration > MAX_VIDEO_DURATION:
            st.error(f"❌ Video too long ({video.duration//60} minutes)")
            return False
        
        # If this is already a segment (small file), we might not need to re-extract
        if video.duration <= (time_to_seconds(end_time) - time_to_seconds(start_time)) + 5:
            if progress_callback:
                progress_callback(70, "✅ Video is already segmented, converting format...")
            
            if video_path.endswith('.mp4') and output_filename.endswith('.mp4'):
                shutil.copy2(video_path, output_filename)
                if progress_callback:
                    progress_callback(85, "✅ File copied successfully!")
                return True
        
        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time) if end_time else start_seconds + 30
        
        # Validate segment length (max 30 minutes)
        segment_duration = end_seconds - start_seconds
        if segment_duration > 1800:  # 30 minutes
            st.warning("⚠️ Segment too long, limiting to 30 minutes")
            end_seconds = start_seconds + 1800
        
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
        
        # Simplified conversion for public deployment
        segment.write_videofile(output_filename)
        
        if progress_callback:
            progress_callback(85, "✅ Video segment saved successfully!")
        
        # Check output file size
        if os.path.exists(output_filename):
            file_size_mb = os.path.getsize(output_filename) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                os.remove(output_filename)
                st.error(f"❌ Output file too large ({file_size_mb:.1f}MB)")
                return False
        
        return os.path.exists(output_filename)
        
    except Exception as e:
        st.error(f"❌ Extraction error: {e}")
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

def clean_filename_safe(title):
    """Clean filename with additional safety for public deployment"""
    if not title or not isinstance(title, str):
        return "untitled"
    
    # Limit length for public deployment
    title = title[:100]  # Max 100 characters
    
    # Remove invalid filename characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', title)
    # Remove URLs and extra spaces
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Remove problematic characters
    cleaned = re.sub(r'["\'"`,]', '', cleaned)
    cleaned = re.sub(r'[{}[\];]', '_', cleaned)
    
    # Ensure valid filename
    if not cleaned or cleaned.isspace():
        cleaned = "untitled"
        
    return cleaned

# ============================================================================
# AUTOMATIC CLEANUP SYSTEM
# ============================================================================

def cleanup_user_files():
    """Clean up user's temporary files"""
    try:
        user_temp_dir = get_user_temp_dir()
        if os.path.exists(user_temp_dir):
            shutil.rmtree(user_temp_dir, ignore_errors=True)
    except:
        pass

def cleanup_old_temp_dirs():
    """Clean up old temporary directories (background task)"""
    try:
        base_temp = Path(tempfile.gettempdir()) / "youtube_extractor"
        if not base_temp.exists():
            return
            
        current_time = time_module.time()
        for temp_dir in base_temp.iterdir():
            if temp_dir.is_dir():
                try:
                    dir_age = current_time - temp_dir.stat().st_mtime
                    if dir_age > TEMP_DIR_RETENTION:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    continue
    except:
        pass

# Register cleanup on exit
atexit.register(cleanup_user_files)

# ============================================================================
# PUBLIC UI WITH ENHANCED FEATURES
# ============================================================================

def main():
    # Add usage warning for public deployment
    st.markdown("""
    ---
    🌐 **Public Demo Version** | 
    ⚠️ **Limits**: Max {duration}min videos, {size}MB files, {chapters} chapters | 
    🔄 **Auto-cleanup**: Files deleted after session ends
    ---
    """.format(
        duration=MAX_VIDEO_DURATION//60,
        size=MAX_FILE_SIZE_MB,
        chapters=MAX_CHAPTERS
    ))
    
    st.title("🎬 YouTube Chapters Extractor")
    st.markdown("Extract video chapters from YouTube videos based on timestamps in descriptions")
    
    # Initialize session state
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
            # Enhanced cleanup for public deployment
            cleanup_user_files()
            st.session_state.timestamps = []
            st.session_state.video_title = ""
            st.session_state.current_url = ""
            st.session_state.extracted_files = []
            st.success("✅ Cleared! Ready for new URL.")
            st.rerun()
    
    # Analysis section
    if analyze_button:
        if not url.strip():
            st.error("Please enter a YouTube URL")
            return
        
        # Check system resources before processing
        if not check_system_resources():
            return
        
        st.session_state.current_url = url
        
        with st.spinner("Analyzing video..."):
            title, description, info = get_video_info_safe(url)
            
            if not title:
                return
            
            timestamps = extract_timestamps(description)
            
            if not timestamps:
                st.warning("⚠️ No timestamps found in video description.")
                with st.expander("🔍 Debug: View Description (First 500 chars)"):
                    st.text(description[:500] if description else "No description found")
                
                st.session_state.video_title = title
            else:
                st.session_state.timestamps = timestamps
                st.session_state.video_title = title
                
                st.success(f"🎬 **Video:** {title}")
                st.success(f"📊 **Found {len(timestamps)} chapters** (limit: {MAX_CHAPTERS})")
    
    # Full video download option
    if st.session_state.video_title and not st.session_state.timestamps:
        st.header("📥 Full Video Download")
        st.info("⚠️ No chapters were found in this video's description.")
        st.info(f"💡 **Option**: Download the entire video (max {MAX_FILE_SIZE_MB}MB)")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            download_complete = st.button("📥 Get Complete Video", type="primary", key="full_video_download_main")
        
        if download_complete:
            if not check_system_resources():
                return
                
            st.header("📥 Processing Complete Video Download")
            
            current_url = st.session_state.current_url
            current_title = st.session_state.video_title
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("🔍 Step 1/4 (10%): Preparing download...")
                progress_bar.progress(10)
                
                def download_progress_callback(percent, message):
                    overall_progress = 10 + (percent / 100) * 70
                    progress_bar.progress(int(overall_progress))
                    status_text.text(f"📥 Step 2/4 ({overall_progress:.0f}%): {message}")
                
                video_path = download_video_safe(current_url, progress_callback=download_progress_callback)
                
                if not video_path:
                    st.error("❌ Failed to download video.")
                    return
                
                status_text.text("📋 Step 3/4 (85%): Saving video...")
                progress_bar.progress(85)
                
                clean_title = clean_filename_safe(current_title)
                output_dir = get_user_output_dir()
                output_filename = os.path.join(output_dir, f"{clean_title}.mp4")
                
                shutil.copy2(video_path, output_filename)
                
                status_text.text("✅ Step 4/4 (100%): Complete!")
                progress_bar.progress(100)
                
                st.success("🎉 **Complete video downloaded successfully!**")
                
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
                st.error(f"❌ Error: {e}")
                progress_bar.progress(0)
            finally:
                # Cleanup temp files
                if 'video_path' in locals() and video_path:
                    try:
                        os.remove(video_path)
                    except:
                        pass
    
    # Chapter selection
    if st.session_state.timestamps:
        st.header("📝 Chapter Selection")
        
        chapter_options = ["🎯 First Chapter Only", "📚 All Chapters"]
        for i, (time, desc) in enumerate(st.session_state.timestamps, 1):
            chapter_options.append(f"{time} - {desc}")
        
        selected_option = st.selectbox(
            "Choose a chapter to extract:",
            chapter_options,
            help="Select from the list of chapters"
        )
        
        if st.button("🚀 Extract selected chapter", type="primary"):
            if not check_system_resources():
                return
                
            current_url = st.session_state.current_url
            if not current_url.strip():
                st.error("Please enter a YouTube URL")
                return
            
            # Determine chapters to extract
            if selected_option == "🎯 First Chapter Only":
                chapters_to_extract = [st.session_state.timestamps[0]]
            elif selected_option == "📚 All Chapters":
                chapters_to_extract = st.session_state.timestamps
            else:
                selected_timestamp = selected_option.split(" - ")[0]
                chapters_to_extract = [ts for ts in st.session_state.timestamps if ts[0] == selected_timestamp]
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("🔍 Step 1/4 (5%): Preparing extraction...")
                progress_bar.progress(5)
                
                def download_progress_callback(percent, message):
                    overall_progress = 5 + (percent / 100) * 30
                    progress_bar.progress(int(overall_progress))
                    status_text.text(f"📥 Step 2/4 ({overall_progress:.0f}%): {message}")
                
                # Download video
                video_path = download_video_safe(current_url, progress_callback=download_progress_callback)
                
                if not video_path:
                    st.error("❌ Failed to download video.")
                    return
                
                status_text.text("✂️ Step 3/4 (40%): Extracting chapters...")
                progress_bar.progress(40)
                
                # Extract chapters
                extracted_files = []
                output_dir = get_user_output_dir()
                
                for i, (start_time, segment_title) in enumerate(chapters_to_extract):
                    # Calculate end time
                    chapter_index = st.session_state.timestamps.index((start_time, segment_title))
                    if chapter_index + 1 < len(st.session_state.timestamps):
                        end_time = st.session_state.timestamps[chapter_index + 1][0]
                    else:
                        start_seconds = time_to_seconds(start_time)
                        end_seconds = start_seconds + 60
                        end_time = f"{end_seconds//60}:{end_seconds%60:02d}"
                    
                    clean_title = clean_filename_safe(segment_title)
                    output_filename = os.path.join(output_dir, f"{i+1:02d}_{clean_title}.mp4")
                    
                    def extraction_progress_callback(percent, message):
                        base_progress = 40 + (i / len(chapters_to_extract)) * 50
                        progress_bar.progress(int(base_progress))
                        status_text.text(f"🎬 Step 3/4 ({base_progress:.0f}%): Chapter {i+1}/{len(chapters_to_extract)} - {message}")
                    
                    success = extract_segment_safe(video_path, start_time, end_time, output_filename, extraction_progress_callback)
                    
                    if success:
                        extracted_files.append(output_filename)
                        if output_filename not in st.session_state.extracted_files:
                            st.session_state.extracted_files.append(output_filename)
                        st.success(f"✅ Chapter {i+1}/{len(chapters_to_extract)} extracted: {segment_title}")
                    else:
                        st.error(f"❌ Failed to extract chapter {i+1}: {segment_title}")
                
                status_text.text("✅ Step 4/4 (100%): Extraction complete!")
                progress_bar.progress(100)
                
                if extracted_files:
                    st.success(f"🎉 **SUCCESS! {len(extracted_files)} chapter(s) extracted!**")
                else:
                    st.error("❌ No chapters were extracted successfully.")
                    
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                progress_bar.progress(0)
            finally:
                # Cleanup temp files
                if 'video_path' in locals() and video_path:
                    try:
                        os.remove(video_path)
                    except:
                        pass
    
    # Persistent results section
    if st.session_state.extracted_files:
        st.header("📁 Extracted Files")
        st.markdown("*Download any of your extracted chapters (files will be deleted when you close the browser):*")
        
        for i, filename in enumerate(st.session_state.extracted_files):
            if os.path.exists(filename):
                file_size = os.path.getsize(filename) / (1024 * 1024)
                
                basename = os.path.basename(filename)
                chapter_name = basename.replace('.mp4', '')
                if '_' in chapter_name and chapter_name[:2].isdigit():
                    chapter_num = chapter_name[:2]
                    chapter_title = chapter_name[3:]
                else:
                    chapter_num = str(i+1)
                    chapter_title = chapter_name
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**Chapter {chapter_num}:** {chapter_title}")
                    st.write(f"📍 `{os.path.basename(filename)}`")
                
                with col2:
                    st.metric("Size", f"{file_size:.1f} MB")
                
                with col3:
                    with open(filename, 'rb') as file:
                        st.download_button(
                            label=f"💾 Download",
                            data=file,
                            file_name=os.path.basename(filename),
                            mime="video/mp4",
                            key=f"public_download_{i}"
                        )
                
                st.divider()
    
    # Background cleanup (runs periodically)
    if int(time_module.time()) % CLEANUP_INTERVAL == 0:
        cleanup_old_temp_dirs()

if __name__ == "__main__":
    main()
