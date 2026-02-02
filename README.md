# YouTube Video Summarizer

Summarize YouTube videos using Claude AI. Supports single videos or entire channels.

## Features

- **Single Video Summarization** - Paste a YouTube URL and get a structured summary
- **Batch Channel Processing** - Summarize multiple videos from a channel
- **Multi-language Support** - Works with English and Chinese videos, reports always in English
- **Export Formats** - Download as Markdown, HTML, PDF, or Word (.docx)

## Setup

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the app: `streamlit run app.py`

## API Keys Required

- **Anthropic API Key** (required) - Get one at https://console.anthropic.com/
- **YouTube Data API Key** (optional, for batch processing) - Get one at https://console.cloud.google.com/

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to https://share.streamlit.io/
3. Connect your GitHub repo
4. Add your API keys in Settings → Secrets:
   ```
   ANTHROPIC_API_KEY = "your-key-here"
   YOUTUBE_API_KEY = "your-key-here"
   ```

Built with Streamlit and Claude AI.
