import streamlit as st
import anthropic
import re
import os
import io
import tempfile
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from dotenv import load_dotenv
from googleapiclient.discovery import build
import markdown
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Try to import whisper (optional dependency)
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

load_dotenv()

st.set_page_config(
    page_title="YouTube Video Summarizer",
    page_icon="🎬",
    layout="wide",
)

st.title("YouTube Video Summarizer")
st.markdown("Summarize single videos or entire channels. Supports English and Chinese videos.")


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_channel_id(url: str) -> str | None:
    """Extract YouTube channel ID or username from URL."""
    patterns = [
        r'(?:youtube\.com\/channel\/)([a-zA-Z0-9_-]+)',
        r'(?:youtube\.com\/c\/)([a-zA-Z0-9_-]+)',
        r'(?:youtube\.com\/@)([a-zA-Z0-9_-]+)',
        r'(?:youtube\.com\/user\/)([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_channel_videos(channel_identifier: str, youtube_api_key: str, max_results: int = 50) -> list[dict]:
    """Fetch video list from a YouTube channel."""
    youtube = build('youtube', 'v3', developerKey=youtube_api_key)

    # First, try to get channel ID if we have a username/handle
    if not channel_identifier.startswith('UC'):
        # Search for the channel
        search_response = youtube.search().list(
            q=channel_identifier,
            type='channel',
            part='id,snippet',
            maxResults=1
        ).execute()

        if not search_response.get('items'):
            return []

        channel_id = search_response['items'][0]['id']['channelId']
    else:
        channel_id = channel_identifier

    # Get the uploads playlist ID
    channel_response = youtube.channels().list(
        id=channel_id,
        part='contentDetails,snippet'
    ).execute()

    if not channel_response.get('items'):
        return []

    channel_title = channel_response['items'][0]['snippet']['title']
    uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Fetch videos from uploads playlist
    videos = []
    next_page_token = None

    while len(videos) < max_results:
        playlist_response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part='snippet',
            maxResults=min(50, max_results - len(videos)),
            pageToken=next_page_token
        ).execute()

        for item in playlist_response.get('items', []):
            videos.append({
                'video_id': item['snippet']['resourceId']['videoId'],
                'title': item['snippet']['title'],
                'channel': channel_title,
                'published_at': item['snippet']['publishedAt'],
            })

        next_page_token = playlist_response.get('nextPageToken')
        if not next_page_token:
            break

    return videos


def transcribe_with_whisper(video_id: str, model_size: str = "base") -> tuple[str, str]:
    """Download audio from YouTube and transcribe with Whisper.

    Returns: (transcript_text, language_code)
    """
    if not WHISPER_AVAILABLE:
        raise RuntimeError("Whisper is not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")

        # Download audio using yt-dlp
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            "yt-dlp",
            "-x",  # Extract audio
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--js-runtimes", "node",
            "-o", audio_path,
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to download audio: {result.stderr}")

        # Find the actual audio file (yt-dlp may add extension)
        audio_files = [f for f in os.listdir(tmpdir) if f.endswith(('.mp3', '.m4a', '.webm', '.opus'))]
        if not audio_files:
            raise RuntimeError("No audio file found after download")

        actual_audio_path = os.path.join(tmpdir, audio_files[0])

        # Load Whisper model and transcribe
        model = whisper.load_model(model_size)
        result = model.transcribe(actual_audio_path)

        transcript_text = result["text"]
        language = result.get("language", "en")

        return transcript_text, language


def get_transcript(video_id: str, preferred_languages: list[str] = None, use_whisper_fallback: bool = True) -> tuple[str, str]:
    """Fetch transcript from YouTube video with language preference.

    Returns: (transcript_text, language_code)
    """
    if preferred_languages is None:
        preferred_languages = ['en', 'zh-Hans', 'zh-Hant', 'zh', 'zh-CN', 'zh-TW']

    ytt_api = YouTubeTranscriptApi()

    # Try to fetch with preferred languages directly
    try:
        transcript = ytt_api.fetch(video_id, languages=preferred_languages)
        # Determine which language was used
        lang_code = 'en'  # default
        for lang in preferred_languages:
            if lang.startswith('zh'):
                # Check if transcript contains Chinese characters
                sample = str(transcript[:100]) if transcript else ""
                if any('\u4e00' <= char <= '\u9fff' for char in sample):
                    lang_code = lang
                    break

        full_text = " ".join([entry.text for entry in transcript])
        return full_text, lang_code
    except Exception:
        pass

    # Fallback: try listing available transcripts
    try:
        transcript_list = ytt_api.list(video_id)

        # Try to find a transcript in preferred languages
        transcript = None
        lang_code = None

        # First try manually created transcripts
        for lang in preferred_languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                lang_code = lang
                break
            except NoTranscriptFound:
                continue

        # Then try auto-generated transcripts
        if transcript is None:
            for lang in preferred_languages:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    lang_code = lang
                    break
                except NoTranscriptFound:
                    continue

        # If still no transcript, get whatever is available
        if transcript is None:
            for t in transcript_list:
                transcript = t
                lang_code = t.language_code
                break

        if transcript is None:
            raise NoTranscriptFound(video_id, preferred_languages, transcript_list)

        fetched = transcript.fetch()
        full_text = " ".join([entry.text for entry in fetched])
        return full_text, lang_code
    except NoTranscriptFound:
        if use_whisper_fallback and WHISPER_AVAILABLE:
            return transcribe_with_whisper(video_id)
        raise
    except Exception as e:
        if use_whisper_fallback and WHISPER_AVAILABLE:
            return transcribe_with_whisper(video_id)
        raise NoTranscriptFound(video_id, preferred_languages, None) from e


def summarize_with_claude(transcript: str, api_key: str, source_language: str = "en", video_title: str = "") -> str:
    """Send transcript to Claude API for summarization."""
    # Explicitly use real Anthropic API (not local proxy)
    client = anthropic.Anthropic(
        api_key=api_key,
        base_url="https://api.anthropic.com"
    )

    language_note = ""
    if source_language.startswith('zh'):
        language_note = "\n\nNote: This transcript is in Chinese. Please provide the summary report entirely in English."

    title_context = ""
    if video_title:
        title_context = f"\n\nVideo Title: {video_title}"

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"""Please analyze the following YouTube video transcript and create a comprehensive summary report in English.{title_context}{language_note}

Structure your report with these sections:

## Overview
A brief 2-3 sentence summary of what the video is about.

## Key Points
The main ideas or arguments presented in the video as bullet points.

## Detailed Summary
A more detailed breakdown of the content, organized by topic or chronologically.

## Key Takeaways
The most important insights or action items from the video.

## Notable Quotes
Any memorable or significant quotes from the video (if applicable).

---

TRANSCRIPT:
{transcript}""",
            }
        ],
    )
    return message.content[0].text


def convert_to_html(markdown_text: str, title: str = "YouTube Video Summary") -> str:
    """Convert markdown to styled HTML."""
    html_content = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])

    styled_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{ color: #1a1a1a; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
        h2 {{ color: #2c3e50; margin-top: 30px; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 8px; }}
        blockquote {{
            border-left: 4px solid #3498db;
            padding-left: 20px;
            margin-left: 0;
            color: #555;
            font-style: italic;
        }}
        hr {{ border: none; border-top: 1px solid #e0e0e0; margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {html_content}
</body>
</html>"""
    return styled_html


def convert_to_pdf(markdown_text: str, title: str = "YouTube Video Summary") -> bytes:
    """Convert markdown to PDF using weasyprint."""
    from weasyprint import HTML

    html_content = convert_to_html(markdown_text, title)
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes


def convert_to_docx(markdown_text: str, title: str = "YouTube Video Summary") -> bytes:
    """Convert markdown to Word document."""
    doc = Document()

    # Add title
    title_para = doc.add_heading(title, 0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Parse markdown and add content
    lines = markdown_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('## '):
            doc.add_heading(line[3:], level=1)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=2)
        elif line.startswith('- ') or line.startswith('* '):
            para = doc.add_paragraph(line[2:], style='List Bullet')
        elif line.startswith('---'):
            doc.add_paragraph('_' * 50)
        else:
            # Remove markdown bold/italic for plain text
            clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
            if clean_line:
                doc.add_paragraph(clean_line)

    # Save to bytes
    doc_bytes = io.BytesIO()
    doc.save(doc_bytes)
    doc_bytes.seek(0)
    return doc_bytes.getvalue()


# Sidebar settings
api_key = os.getenv("ANTHROPIC_API_KEY", "")
youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")

with st.sidebar:
    st.header("Settings")
    user_api_key = st.text_input(
        "Anthropic API Key",
        value=api_key,
        type="password",
        help="Enter your Anthropic API key. Get one at https://console.anthropic.com/",
    )

    user_youtube_api_key = st.text_input(
        "YouTube Data API Key",
        value=youtube_api_key,
        type="password",
        help="Required for channel batch processing. Get one at https://console.cloud.google.com/",
    )

    st.markdown("---")
    st.markdown("### Export Formats")
    export_format = st.selectbox(
        "Choose export format",
        ["Markdown (.md)", "HTML (.html)", "PDF (.pdf)", "Word/Google Docs (.docx)"]
    )

    st.markdown("---")
    st.markdown("### How to use")
    st.markdown("""
    **Single Video:**
    1. Paste a YouTube video URL
    2. Click 'Summarize Video'

    **Batch (Channel):**
    1. Enter YouTube API key
    2. Paste a channel URL
    3. Select number of videos
    4. Click 'Process Channel'
    """)

# Main content - tabs for single vs batch
tab1, tab2 = st.tabs(["Single Video", "Batch (Channel)"])

with tab1:
    st.subheader("Summarize a Single Video")
    youtube_url = st.text_input(
        "YouTube Video URL",
        placeholder="https://www.youtube.com/watch?v=...",
        key="single_url"
    )

    if st.button("Summarize Video", type="primary", use_container_width=True):
        if not user_api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
        elif not youtube_url:
            st.error("Please enter a YouTube URL.")
        else:
            video_id = extract_video_id(youtube_url)

            if not video_id:
                st.error("Could not extract video ID from the URL. Please check the URL format.")
            else:
                try:
                    with st.status("Processing video...", expanded=True) as status:
                        st.write("Fetching transcript...")
                        try:
                            transcript, lang_code = get_transcript(video_id, use_whisper_fallback=False)
                            transcript_source = "YouTube captions"
                        except (NoTranscriptFound, TranscriptsDisabled, Exception):
                            if WHISPER_AVAILABLE:
                                st.write("No captions found. Using Whisper to transcribe audio...")
                                st.write("(This may take a few minutes for longer videos)")
                                transcript, lang_code = transcribe_with_whisper(video_id)
                                transcript_source = "Whisper transcription"
                            else:
                                raise NoTranscriptFound(video_id, [], None)

                        lang_display = "Chinese" if lang_code.startswith('zh') else "English"
                        st.write(f"Transcript fetched via {transcript_source} ({len(transcript):,} characters, {lang_display})")
                        st.write("Generating summary with Claude...")

                        summary = summarize_with_claude(transcript, user_api_key, lang_code)
                        status.update(label="Complete!", state="complete", expanded=False)

                    st.markdown("---")
                    st.markdown("## Summary Report")
                    st.markdown(summary)

                    # Export buttons
                    st.markdown("### Download Report")
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.download_button(
                            label="📄 Markdown",
                            data=summary,
                            file_name="youtube_summary.md",
                            mime="text/markdown",
                        )

                    with col2:
                        html_content = convert_to_html(summary)
                        st.download_button(
                            label="🌐 HTML",
                            data=html_content,
                            file_name="youtube_summary.html",
                            mime="text/html",
                        )

                    with col3:
                        try:
                            pdf_content = convert_to_pdf(summary)
                            st.download_button(
                                label="📕 PDF",
                                data=pdf_content,
                                file_name="youtube_summary.pdf",
                                mime="application/pdf",
                            )
                        except Exception as e:
                            st.button("📕 PDF", disabled=True, help=f"PDF generation failed: {e}")

                    with col4:
                        docx_content = convert_to_docx(summary)
                        st.download_button(
                            label="📝 Word/Docs",
                            data=docx_content,
                            file_name="youtube_summary.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )

                except TranscriptsDisabled:
                    st.error("Transcripts are disabled for this video.")
                except NoTranscriptFound:
                    if not WHISPER_AVAILABLE:
                        st.error("No captions found and Whisper is not installed. Install whisper to transcribe videos without captions.")
                    else:
                        st.error("No transcript found for this video. It may not have captions.")
                except VideoUnavailable:
                    st.error("This video is unavailable.")
                except anthropic.AuthenticationError:
                    st.error("Invalid Anthropic API key. Please check your key.")
                except anthropic.RateLimitError:
                    st.error("Rate limit exceeded. Please try again later.")
                except anthropic.APIConnectionError as e:
                    st.error(f"Could not connect to Anthropic API. Check your internet connection. Details: {str(e)}")
                except Exception as e:
                    st.error(f"An error occurred: {type(e).__name__}: {str(e)}")

with tab2:
    st.subheader("Process Entire Channel")
    channel_url = st.text_input(
        "YouTube Channel URL",
        placeholder="https://www.youtube.com/@ChannelName or https://www.youtube.com/channel/UC...",
        key="channel_url"
    )

    max_videos = st.slider("Number of videos to process", min_value=1, max_value=50, value=5)

    if st.button("Process Channel", type="primary", use_container_width=True):
        if not user_api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
        elif not user_youtube_api_key:
            st.error("Please enter your YouTube Data API key in the sidebar for channel processing.")
        elif not channel_url:
            st.error("Please enter a YouTube channel URL.")
        else:
            channel_id = extract_channel_id(channel_url)

            if not channel_id:
                st.error("Could not extract channel ID from the URL. Please check the URL format.")
            else:
                try:
                    with st.status("Processing channel...", expanded=True) as status:
                        st.write("Fetching video list...")
                        videos = get_channel_videos(channel_id, user_youtube_api_key, max_videos)

                        if not videos:
                            st.error("No videos found for this channel.")
                        else:
                            st.write(f"Found {len(videos)} videos. Processing...")

                            all_summaries = []
                            progress_bar = st.progress(0)

                            for i, video in enumerate(videos):
                                st.write(f"Processing: {video['title'][:50]}...")
                                try:
                                    transcript, lang_code = get_transcript(video['video_id'])
                                    summary = summarize_with_claude(
                                        transcript,
                                        user_api_key,
                                        lang_code,
                                        video['title']
                                    )
                                    all_summaries.append({
                                        'title': video['title'],
                                        'video_id': video['video_id'],
                                        'summary': summary,
                                        'language': lang_code,
                                    })
                                except Exception as e:
                                    all_summaries.append({
                                        'title': video['title'],
                                        'video_id': video['video_id'],
                                        'summary': f"Error: {str(e)}",
                                        'language': 'unknown',
                                    })

                                progress_bar.progress((i + 1) / len(videos))

                            status.update(label="Complete!", state="complete", expanded=False)

                    # Display results
                    st.markdown("---")
                    st.markdown("## Channel Summary Report")

                    # Combined report
                    combined_report = f"# Channel Video Summaries\n\nProcessed {len(all_summaries)} videos\n\n"

                    for item in all_summaries:
                        combined_report += f"---\n\n# {item['title']}\n\n"
                        combined_report += f"**Video URL:** https://www.youtube.com/watch?v={item['video_id']}\n\n"
                        combined_report += f"{item['summary']}\n\n"

                    # Show individual summaries in expanders
                    for item in all_summaries:
                        with st.expander(f"📺 {item['title'][:60]}..."):
                            st.markdown(f"[Watch Video](https://www.youtube.com/watch?v={item['video_id']})")
                            st.markdown(item['summary'])

                    # Export combined report
                    st.markdown("### Download Combined Report")
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.download_button(
                            label="📄 Markdown",
                            data=combined_report,
                            file_name="channel_summaries.md",
                            mime="text/markdown",
                            key="batch_md"
                        )

                    with col2:
                        html_content = convert_to_html(combined_report, "Channel Summary Report")
                        st.download_button(
                            label="🌐 HTML",
                            data=html_content,
                            file_name="channel_summaries.html",
                            mime="text/html",
                            key="batch_html"
                        )

                    with col3:
                        try:
                            pdf_content = convert_to_pdf(combined_report, "Channel Summary Report")
                            st.download_button(
                                label="📕 PDF",
                                data=pdf_content,
                                file_name="channel_summaries.pdf",
                                mime="application/pdf",
                                key="batch_pdf"
                            )
                        except Exception as e:
                            st.button("📕 PDF", disabled=True, help=f"PDF generation failed: {e}", key="batch_pdf_disabled")

                    with col4:
                        docx_content = convert_to_docx(combined_report, "Channel Summary Report")
                        st.download_button(
                            label="📝 Word/Docs",
                            data=docx_content,
                            file_name="channel_summaries.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key="batch_docx"
                        )

                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>Built with Streamlit and Claude AI | Supports English & Chinese videos</div>",
    unsafe_allow_html=True,
)
