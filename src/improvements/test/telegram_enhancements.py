import re

# Simple dependency checks
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YOUTUBE_ENABLED = True
except ImportError:
    YOUTUBE_ENABLED = False

try:
    import openai
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False


class TelegramEnhancementManager:
    @staticmethod
    def extract_youtube_transcript(text: str) -> str:
        """Checks for YouTube URLs in text and attempts to fetch transcripts."""
        if not YOUTUBE_ENABLED:
            return text
            
        youtube_regex = (
            r'(https?://)?(www\.)?'
            r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
            r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        )
        
        match = re.search(youtube_regex, text)
        if not match:
            return text
            
        video_id = match.group(6)
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript = " ".join([t['text'] for t in transcript_list])
            # Append the transcript to the prompt so the council can analyze it
            return f"{text}\n\n[Auto-Extracted YouTube Transcript]:\n{transcript[:15000]}"
        except Exception as e:
            return f"{text}\n\n[Auto-Extracted YouTube Transcript Failed]: {str(e)}"
            
    @staticmethod
    def process_voice_note(audio_file_path: str) -> str:
        """Processes an audio file using OpenAI Whisper API or local equivalent."""
        if not VOICE_ENABLED:
            return "Voice processing is currently disabled (missing 'openai' package or key)."
            
        try:
            # We assume OPENAI_API_KEY is set in .env
            client = openai.OpenAI()
            with open(audio_file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    response_format="text"
                )
            return f"[Voice Note Transcription]: {transcript}"
        except Exception as e:
            return f"Voice processing failed: {str(e)}"
