import subprocess

from tutor_any_lecture.ffmpeg import extract_audio, ffmpeg_exe, media_duration


def test_extract_audio_and_duration(tmp_path):
    # 2 s of sine from ffmpeg lavfi, in a folder with spaces and CJK
    src = tmp_path / "第 1 周" / "tone.wav"
    src.parent.mkdir()
    subprocess.run([ffmpeg_exe(), "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(src)],
                   check=True, capture_output=True)
    assert abs(media_duration(src) - 2.0) < 0.1
    extract_audio(src, tmp_path / "o.wav")
    assert (tmp_path / "o.wav").stat().st_size > 0
