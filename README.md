---
title: Video Summarizer
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
---

# Video Summarizer

Summarize videos from **YouTube, TikTok, Twitter, Bilibili, Vimeo**, and 1000+ platforms using AI.

## Features

- **Multi-Platform Support** - Works with YouTube, TikTok, Twitter/X, Instagram, Bilibili, Vimeo, and 1000+ sites
- **AI-Powered Summaries** - Choose between Google Gemini (free) or Anthropic Claude
- **Auto-Transcription** - Uses Whisper AI when captions aren't available
- **Multi-Language** - Supports English, Chinese, and other languages (reports in English)
- **Export Options** - Download as Markdown, HTML, PDF, or Word
- **Batch Processing** - Summarize entire YouTube channels

## Quick Start

1. Get a free API key:
   - **Google Gemini (Free)**: https://aistudio.google.com/app/apikey
   - **Anthropic Claude ($5+)**: https://console.anthropic.com/
2. Paste any video URL
3. Click "Summarize"

## Supported Platforms

- YouTube, YouTube Shorts
- TikTok, Douyin
- Twitter/X
- Instagram Reels
- Bilibili
- Vimeo, Dailymotion
- Facebook, Twitch
- And 1000+ more via yt-dlp

## API Keys

Each user enters their own API key - keys are not stored on the server.

| Provider | Cost | Get Key |
|----------|------|---------|
| Google Gemini | Free (60 req/min) | [Get Key](https://aistudio.google.com/app/apikey) |
| Anthropic Claude | $5 minimum | [Get Key](https://console.anthropic.com/) |

## Run Locally

```bash
git clone https://github.com/yihanwwww/youtube-summarizer.git
cd youtube-summarizer
pip install -r requirements.txt
streamlit run app.py
```

Built with Streamlit, Whisper, and yt-dlp.
