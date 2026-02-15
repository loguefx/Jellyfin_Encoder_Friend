"""
FFmpeg transcoder for Jellyfin Audio Service.
Converts video files to MP4 with AAC-LC audio while preserving original filenames.
Subtitles from MKV files are extracted to external SRT files.
"""

import os
import subprocess
import logging
import tempfile
import json
import shutil
from pathlib import Path
from typing import Optional, Tuple

import config
import backup
import scanner
import cache

logger = logging.getLogger(__name__)

# #region agent log
DEBUG_LOG_PATH = Path(__file__).parent / ".cursor" / "debug.log"
def _debug_log(hypothesis_id, location, message, data=None):
    try:
        import json
        import time
        # Ensure directory exists
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000)
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # Log to regular logger if debug log fails
        logger.warning(f"Debug log failed: {e}")
# #endregion


def get_output_format(probe_data: dict) -> str:
    """
    Always return 'MP4' for maximum device compatibility.
    MKV files will be converted to MP4, and subtitles will be extracted to SRT files.
    """
    return 'MP4'


def extract_subtitles_to_srt(source_file: Path, subtitle_stream_index: int = 0, output_srt_file: Optional[Path] = None) -> Optional[Path]:
    """
    Extract subtitles from video file to SRT format.
    Returns the path to the created SRT file, or None if extraction failed.
    """
    ffmpeg_path = config.get_ffmpeg_path()
    
    if output_srt_file is None:
        # Create SRT filename: same as video but with .srt extension
        output_srt_file = source_file.with_suffix('.srt')
    
    try:
        # Extract subtitle stream to SRT format
        # FFmpeg will auto-detect and convert text-based subtitle formats (ASS, SSA, SRT, VTT, etc.)
        # Note: Image-based subtitles (PGS, VOBSUB) cannot be converted to SRT by FFmpeg
        cmd = [
            ffmpeg_path,
            '-i', str(source_file),
            '-map', f'0:s:{subtitle_stream_index}',  # Map subtitle stream by index
            '-c:s', 'srt',  # Output format: SRT
            '-y',  # Overwrite output file
            str(output_srt_file)
        ]
        
        logger.info(f"Extracting subtitles to: {output_srt_file}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0 and output_srt_file.exists():
            logger.info(f"Subtitle extraction successful: {output_srt_file}")
            return output_srt_file
        else:
            logger.warning(f"Subtitle extraction failed: {result.stderr[-500:] if result.stderr else 'No error message'}")
            if output_srt_file.exists():
                output_srt_file.unlink()
            return None
    except Exception as e:
        logger.error(f"Error extracting subtitles: {e}")
        if output_srt_file and output_srt_file.exists():
            try:
                output_srt_file.unlink()
            except:
                pass
        return None


def convert_to_mp4_aac(source_file: Path, create_backup_first: bool = True, progress_callback=None) -> Tuple[bool, Optional[str]]:
    """
    Convert video file to MP4 with AAC-LC audio.
    All files are converted to MP4 for maximum device compatibility.
    If source file has subtitles, they will be extracted to external SRT files.
    Preserves original filename and location.
    Returns (success, error_message).
    """
    # #region agent log
    _debug_log("ALL", "transcoder.py:21", "convert_to_mp4_aac entry", {"source_file": str(source_file), "create_backup_first": create_backup_first})
    # #endregion
    
    if not source_file.exists():
        error_msg = f"Source file does not exist: {source_file}"
        logger.error(error_msg)
        # #region agent log
        _debug_log("ALL", "transcoder.py:28", "Source file does not exist", {"source_file": str(source_file)})
        # #endregion
        return False, error_msg
    
    # Create backup first if requested
    if create_backup_first:
        # #region agent log
        _debug_log("ALL", "transcoder.py:33", "Creating backup", {"source_file": str(source_file)})
        # #endregion
        backup_path = backup.create_backup(source_file)
        # #region agent log
        _debug_log("ALL", "transcoder.py:35", "Backup result", {"backup_path": str(backup_path) if backup_path else None})
        # #endregion
        if backup_path is None:
            error_msg = f"Failed to create backup for {source_file}"
            logger.error(error_msg)
            # #region agent log
            _debug_log("ALL", "transcoder.py:36", "Backup creation failed", {"source_file": str(source_file)})
            # #endregion
            return False, error_msg
    
    # Get audio settings from config
    audio_settings = config.get_audio_settings()
    ffmpeg_path = config.get_ffmpeg_path()
    allowed_channels = audio_settings.get('allowed_channels', [2, 6])
    
    # Probe source file to detect original audio channels and streams
    probe_data = scanner.probe_video_file(source_file)
    if not probe_data:
        return False, "Failed to probe video file - file may be corrupted or inaccessible"
    
    streams = probe_data.get('streams', [])
    if not streams:
        return False, "No streams found in video file"
    
    audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
    if not audio_streams:
        return False, "No audio streams found in video file - cannot convert audio"
    
    subtitle_streams = [s for s in streams if s.get('codec_type') == 'subtitle']
    has_subtitles = len(subtitle_streams) > 0
    
    # Detect source container format
    format_name = probe_data.get('format', {}).get('format_name', '').lower()
    is_source_mkv = 'matroska' in format_name or 'mkv' in format_name
    
    # Always output MP4 for maximum device compatibility
    output_ext = '.mp4'
    output_format = 'MP4'
    
    # Determine final output filename (what the MP4 will be named)
    # This ensures SRT files match the final video filename for Jellyfin recognition
    output_file = source_file.with_suffix(output_ext)
    
    # Extract subtitles from MKV files before conversion
    # Use the final output filename (MP4 name) for the SRT file so it matches the video file
    extracted_srt_files = []
    if is_source_mkv and has_subtitles:
        logger.info(f"Source is MKV with {len(subtitle_streams)} subtitle stream(s), extracting to SRT files")
        # Extract first subtitle stream (most common use case)
        # Use output_file to ensure SRT name matches final MP4 filename
        # This ensures Jellyfin can recognize the subtitle file
        srt_file = extract_subtitles_to_srt(source_file, subtitle_stream_index=0, output_srt_file=output_file.with_suffix('.srt'))
        if srt_file:
            extracted_srt_files.append(srt_file)
            logger.info(f"Extracted subtitle to: {srt_file} (matches video filename for Jellyfin recognition)")
        else:
            logger.warning("Failed to extract subtitles - conversion will continue without subtitles")
    elif has_subtitles:
        logger.info(f"Source has {len(subtitle_streams)} subtitle stream(s), but subtitles in MP4 are not widely supported")
        logger.info("Note: Subtitles will not be included in output MP4 file")
    
    original_channels = 2  # Default to stereo
    if audio_streams:
        try:
            detected_channels = int(audio_streams[0].get('channels', 2))
            # If original has allowed channel count (2.0 or 5.1), preserve it
            if detected_channels in allowed_channels:
                original_channels = detected_channels
                logger.info(f"Preserving original audio channels: {original_channels}")
            else:
                # Otherwise, default to stereo
                logger.info(f"Original audio has {detected_channels} channels (not in allowed list {allowed_channels}), converting to stereo")
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse audio channels, defaulting to stereo: {e}")
            original_channels = 2
    
    # Output file already determined above (for subtitle extraction)
    # output_file is already set: source_file.with_suffix(output_ext)
    
    # If source extension matches output extension, use temporary file then replace
    # Otherwise, output will be with new extension
    temp_output = None
    if source_file.suffix.lower() == output_ext.lower():
        # Use a unique temp filename to avoid conflicts
        import time
        temp_suffix = f"_temp_{os.getpid()}_{int(time.time() * 1000)}"
        temp_output = source_file.parent / f"{source_file.stem}{temp_suffix}{output_ext}"
        # Make sure temp file doesn't already exist
        counter = 0
        while temp_output.exists():
            counter += 1
            temp_output = source_file.parent / f"{source_file.stem}{temp_suffix}_{counter}{output_ext}"
        final_output = temp_output
        logger.info(f"Using temporary output file: {final_output}")
    else:
        # Output will have different extension
        # Check if output already exists and handle it
        if output_file.exists():
            logger.warning(f"Output file already exists: {output_file}")
            # This shouldn't happen if we're converting, but handle it gracefully
        final_output = output_file
    
    try:
        # Check if output directory exists and is writable
        output_dir = final_output.parent
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create output directory: {e}"
        
        # Check if file is accessible (not locked)
        try:
            with open(source_file, 'rb') as test_file:
                test_file.read(1)
        except (IOError, PermissionError) as e:
            return False, f"Source file is locked or inaccessible: {e}"
        
        # Helper function for audio copy fallback (for exit code 69)
        def _try_audio_copy_fallback(source_file, final_output, ffmpeg_path, output_format, output_ext, source_size, progress_callback):
            """Try copying audio stream as fallback when re-encoding fails with exit code 69."""
            logger.info("Trying fallback: copying audio stream (may not meet compliance requirements)")
            
            # Build fallback command with -c:a copy (MP4 output, no subtitles)
            fallback_cmd = [
                ffmpeg_path,
                '-i', str(source_file),
                '-map', '0:v',  # Map video stream
                '-map', '0:a',  # Map audio stream(s)
                '-c:v', 'copy',
                '-c:a', 'copy',  # Copy audio without re-encoding
                '-fflags', '+genpts+igndts+ignidx',
                '-avoid_negative_ts', 'make_zero',
                '-max_muxing_queue_size', '1024',
                '-movflags', '+faststart',  # MP4 optimization
                '-y',
            ]
            
            if output_format == 'MP4':
                fallback_cmd.extend(['-movflags', '+faststart'])
            
            # No subtitle copy for MP4 output (subtitles extracted separately)
            
            # Use a different temp filename for fallback
            fallback_output = final_output.parent / f"{final_output.stem}_fallback{final_output.suffix}"
            fallback_cmd.append(str(fallback_output))
            
            logger.info(f"Fallback FFmpeg command: {' '.join(fallback_cmd)}")
            
            try:
                process = subprocess.Popen(
                    fallback_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = process.communicate()
                
                if process.returncode == 0 and fallback_output.exists():
                    fallback_size = fallback_output.stat().st_size
                    if fallback_size > source_size // 100:  # At least 1% of source size
                        logger.warning("Fallback succeeded: audio stream copied (file may not meet compliance requirements)")
                        # Replace the failed output with fallback output
                        if final_output.exists():
                            final_output.unlink()
                        shutil.move(str(fallback_output), str(final_output))
                        if progress_callback:
                            try:
                                progress_callback(100)
                            except:
                                pass
                        # Perform file replacement (same as successful conversion)
                        # Check if we need to replace source file
                        if temp_output:  # Source and output have same extension
                            try:
                                # Verify final_output exists before attempting move
                                if not final_output.exists():
                                    error_msg = f"Fallback converted file does not exist: {final_output}"
                                    logger.error(error_msg)
                                    return False, f"Fallback conversion succeeded but output file missing: {error_msg}"
                                
                                # Try to delete source file with retries
                                import time
                                max_retries = 3
                                retry_delay = 1.0
                                for attempt in range(max_retries):
                                    try:
                                        if source_file.exists():
                                            source_file.unlink()
                                            break
                                    except (OSError, PermissionError) as e:
                                        if attempt < max_retries - 1:
                                            logger.warning(f"Failed to delete source file (attempt {attempt+1}/{max_retries}): {e}. Retrying...")
                                            time.sleep(retry_delay)
                                        else:
                                            logger.warning(f"Failed to delete source file after {max_retries} attempts: {e}. Attempting move anyway...")
                                
                                # Move with retry logic
                                move_success = False
                                for move_attempt in range(max_retries):
                                    try:
                                        if not final_output.exists():
                                            error_msg = f"Fallback converted file disappeared before move: {final_output}"
                                            logger.error(error_msg)
                                            return False, error_msg
                                        shutil.move(str(final_output), str(source_file))
                                        move_success = True
                                        break
                                    except (OSError, PermissionError, FileNotFoundError) as move_error:
                                        if move_attempt < max_retries - 1:
                                            logger.warning(f"Move failed (attempt {move_attempt + 1}/{max_retries}): {move_error}. Retrying...")
                                            time.sleep(retry_delay)
                                        else:
                                            raise
                                
                                if not move_success:
                                    error_msg = f"Failed to move fallback file after {max_retries} attempts"
                                    logger.error(error_msg)
                                    return False, f"Fallback conversion succeeded but file replacement failed: {error_msg}"
                                
                                logger.info(f"Successfully replaced source file: {source_file}")
                                # Cache the converted file (no subtitle file for fallback conversions)
                                cache_success = cache.cache_file_converted(source_file, original_path=source_file, subtitle_file=None)
                                if cache_success:
                                    logger.info(f"Converted file cached (fallback): {source_file}")
                                else:
                                    logger.warning(f"Failed to cache converted file (fallback): {source_file}")
                                return True, "Conversion completed using fallback (audio copied, may not meet compliance requirements)"
                            except Exception as e:
                                logger.error(f"Failed to replace source file: {e}")
                                return False, f"Fallback conversion succeeded but file replacement failed: {e}"
                        else:
                            # Output has different extension, source remains, output is separate
                            # Cache the converted file (no subtitle file for fallback conversions)
                            cache_success = cache.cache_file_converted(final_output, source_file, subtitle_file=None)
                            if cache_success:
                                logger.info(f"Converted file cached (fallback): {final_output}")
                            else:
                                logger.warning(f"Failed to cache converted file (fallback): {final_output}")
                            return True, "Conversion completed using fallback (audio copied, may not meet compliance requirements)"
                    else:
                        fallback_output.unlink()
                        return False, "Fallback conversion produced invalid output file"
                else:
                    if fallback_output.exists():
                        fallback_output.unlink()
                    logger.error(f"Fallback conversion also failed: {stderr[-500:] if stderr else 'No error message'}")
                    return False, "Both primary and fallback conversion methods failed"
            except Exception as e:
                if fallback_output.exists():
                    try:
                        fallback_output.unlink()
                    except:
                        pass
                logger.error(f"Exception during fallback conversion: {e}")
                return False, f"Fallback conversion failed with exception: {e}"
        
        # Build FFmpeg command
        # Always output MP4 - map video and audio only (no subtitles in MP4)
        cmd = [
            ffmpeg_path,
            '-i', str(source_file),
            '-map', '0:v',  # Map video stream
            '-map', '0:a',  # Map audio stream(s)
            '-c:v', 'copy',  # Copy video codec (no re-encoding)
            '-c:a', audio_settings.get('codec', 'aac'),
            '-profile:a', audio_settings.get('profile', 'aac_low'),
            '-b:a', audio_settings.get('bitrate', '192k'),
            '-ac', str(original_channels),  # Preserve original channels if allowed (2.0 or 5.1), otherwise stereo
            '-err_detect', 'ignore_err',  # Ignore decode errors and continue (handles corrupted streams)
            '-fflags', '+genpts+igndts+ignidx',  # Generate presentation timestamps, ignore decode timestamps and index (handles corrupted data)
            '-avoid_negative_ts', 'make_zero',  # Handle negative timestamps from corrupted data
            '-max_muxing_queue_size', '1024',  # Increase muxing queue size to handle problematic streams
            '-movflags', '+faststart',  # Optimize MP4 for streaming
            '-y',  # Overwrite output file
        ]
        
        # Note: Subtitles are not included in MP4 output
        # They are extracted to SRT files separately (for MKV sources) or ignored (for MP4 sources)
        if has_subtitles:
            logger.info(f"File has {len(subtitle_streams)} subtitle stream(s) - subtitles will not be included in MP4 output")
            if extracted_srt_files:
                logger.info(f"Subtitles extracted to external SRT files: {[str(f) for f in extracted_srt_files]}")
        
        cmd.append(str(final_output))
        
        logger.info(f"Converting: {source_file} -> {final_output}")
        logger.info(f"FFmpeg command: {' '.join(cmd)}")
        logger.info(f"Audio settings: codec={audio_settings.get('codec')}, profile={audio_settings.get('profile')}, bitrate={audio_settings.get('bitrate')}, channels={original_channels}")
        
        # Get source file size for progress estimation (must be before debug log that uses it)
        source_size = source_file.stat().st_size
        
        # #region agent log
        _debug_log("H1", "transcoder.py:127", "FFmpeg command built", {"cmd": cmd, "has_subtitles": has_subtitles, "final_output": str(final_output), "source_size": source_size})
        # #endregion
        
        # Run FFmpeg with progress tracking
        logger.info(f"Starting FFmpeg conversion process...")
        
        # Run FFmpeg - redirect stderr to prevent buffer blocking
        # FFmpeg writes progress to stderr, so we need to read it in a thread
        import threading
        import queue
        
        stderr_queue = queue.Queue()
        stderr_lines = []
        
        # Start FFmpeg process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid bytes instead of crashing
            bufsize=1
        )
        
        def read_stderr():
            """Read stderr in background to prevent buffer blocking."""
            try:
                for line in process.stderr:
                    stderr_lines.append(line)
                    stderr_queue.put(line)
            except:
                pass
        
        # Start thread to read stderr
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # Monitor progress by watching output file size
        import time
        last_progress = 0
        start_time = time.time()
        timeout_seconds = 3600  # 1 hour timeout
        last_log_time = 0
        last_output_size = 0
        no_progress_count = 0
        
        logger.info(f"Monitoring FFmpeg process (PID: {process.pid})...")
        
        while process.poll() is None:
            # Check for timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.error(f"FFmpeg conversion timed out after {timeout_seconds} seconds")
                process.kill()
                process.wait()
                return False, f"Conversion timed out after {timeout_seconds} seconds"
            
            time.sleep(0.5)  # Check every 0.5 seconds
            
            # Log every 30 seconds to show it's still running
            if int(elapsed) % 30 == 0 and int(elapsed) != last_log_time:
                last_log_time = int(elapsed)
                logger.info(f"FFmpeg still running... ({int(elapsed)}s elapsed)")
            
            if final_output.exists():
                try:
                    out_size = final_output.stat().st_size
                    # Estimate progress based on output file size
                    # This is approximate but gives a good indication
                    if source_size > 0:
                        # Output file typically grows, estimate progress
                        # Note: This is rough since we're copying video and re-encoding audio
                        progress_percent = min(95, int((out_size / source_size) * 100))
                        if progress_percent > last_progress:
                            last_progress = progress_percent
                            no_progress_count = 0
                            logger.info(f"Conversion progress: {progress_percent}% (output size: {out_size} bytes)")
                            if progress_callback:
                                try:
                                    progress_callback(progress_percent)
                                except:
                                    pass
                        elif out_size == last_output_size and out_size > 0:
                            no_progress_count += 1
                            # If no progress for 2 minutes, something might be wrong
                            if no_progress_count > 240:  # 240 * 0.5s = 120s = 2 minutes
                                logger.warning(f"No progress detected for 2 minutes. Output size: {out_size} bytes")
                    last_output_size = out_size
                except (OSError, FileNotFoundError):
                    pass
        
        # Wait for stderr thread to finish
        stderr_thread.join(timeout=2)
        
        # Get remaining output
        stdout = process.stdout.read() if process.stdout else ""
        stderr = ''.join(stderr_lines)
        
        returncode = process.returncode
        
        logger.info(f"FFmpeg exit code: {returncode}")
        # #region agent log
        _debug_log("H1", "transcoder.py:245", "FFmpeg process completed", {"returncode": returncode, "stderr_length": len(stderr), "stdout_length": len(stdout)})
        # #endregion
        
        if stdout:
            logger.debug(f"FFmpeg stdout: {stdout[:500]}")  # First 500 chars
        if stderr:
            # Log last 1000 chars of stderr (most recent output)
            stderr_preview = stderr[-1000:] if len(stderr) > 1000 else stderr
            logger.debug(f"FFmpeg stderr (last 1000 chars): {stderr_preview}")
            # Also log any error messages
            if 'error' in stderr.lower() or returncode != 0:
                logger.error(f"FFmpeg error output: {stderr}")
                # #region agent log
                _debug_log("H1", "transcoder.py:255", "FFmpeg error detected", {"returncode": returncode, "stderr_preview": stderr_preview, "full_stderr": stderr})
                # #endregion
        
        # Set progress to 100% when done
        if progress_callback:
            try:
                progress_callback(100)
            except:
                pass
        
        # Check if output file was created successfully, even if returncode != 0
        # FFmpeg may exit with non-zero code due to decode errors, but still produce valid output
        output_valid = False
        if final_output.exists():
            try:
                output_size = final_output.stat().st_size
                # Output file should be at least 1MB (reasonable minimum for a video file)
                min_size = max(source_size // 100, 1024 * 1024)  # 1% of source or 1MB
                if output_size >= min_size:
                    output_valid = True
                    logger.info(f"Output file created successfully: {output_size} bytes (source: {source_size} bytes)")
                    # #region agent log
                    _debug_log("H2", "transcoder.py:298", "Output file size check", {"output_size": output_size, "source_size": source_size})
                    # #endregion
                else:
                    logger.warning(f"Output file seems unusually small: {output_size} bytes (source: {source_size} bytes)")
                    # #region agent log
                    _debug_log("H3", "transcoder.py:305", "Output file too small", {"output_size": output_size, "min_size": min_size, "source_size": source_size})
                    # #endregion
            except Exception as e:
                logger.warning(f"Could not check output file size: {e}")
        
        # If output is valid, treat as success even if returncode != 0
        # This handles cases where FFmpeg completes conversion but exits with error due to decode warnings
        if output_valid:
            logger.info(f"Conversion completed successfully despite FFmpeg exit code {returncode} (output file is valid)")
            # Treat as success - continue to file replacement logic below
        elif returncode != 0:
            # Extract meaningful error message from stderr
            error_lines = stderr.split('\n')
            error_msg_lines = []
            for line in error_lines:
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable', 'corrupt', 'decode']):
                    error_msg_lines.append(line.strip())
            
            # For exit code 69 (decoding failure), include more context
            if returncode == 69:
                logger.warning("FFmpeg exit code 69 detected - this typically indicates a decoding failure")
                logger.warning("Common causes: file corruption, unsupported codecs, or subtitle decoding issues")
                # Include more stderr lines for exit code 69
                if error_msg_lines:
                    error_summary = ' | '.join(error_msg_lines[-10:])  # Last 10 error lines for exit 69
                else:
                    error_summary = stderr[-1000:] if len(stderr) > 1000 else stderr
            else:
                if error_msg_lines:
                    error_summary = ' | '.join(error_msg_lines[-3:])  # Last 3 error lines
                else:
                    error_summary = stderr[-500:] if len(stderr) > 500 else stderr
            
            error_msg = f"FFmpeg conversion failed (exit code {returncode}): {error_summary}"
            logger.error(error_msg)
            logger.error(f"Full FFmpeg stderr: {stderr}")
            
            # #region agent log
            _debug_log("H1", "transcoder.py:error_handling", "FFmpeg conversion failed", {
                "returncode": returncode,
                "error_summary": error_summary[:200],  # Truncate for log
                "stderr_length": len(stderr),
                "has_subtitles": has_subtitles,
                "output_format": output_format,
                "source_file": str(source_file.name),
                "final_output": str(final_output)
            })
            # #endregion
            
            # Clean up failed output
            if final_output.exists():
                try:
                    logger.info(f"Removing failed output file: {final_output}")
                    final_output.unlink()
                except Exception as e:
                    logger.warning(f"Could not remove failed output file: {e}")
            
            # For exit code 69 with subtitles, suggest potential fixes
            if returncode == 69 and has_subtitles:
                logger.warning("Note: Exit code 69 with subtitle files may indicate subtitle decoding issues.")
                logger.warning("The file may be corrupted or use unsupported subtitle formats.")
            
            # For exit code 69 (decode error), try fallback: copy audio stream instead of re-encoding
            # This won't fix compliance issues but may produce a usable output file
            if returncode == 69:
                logger.warning("Attempting fallback: copying audio stream instead of re-encoding (file has corrupted audio data)")
                # Check if source audio is already AAC (copy might work even with corruption)
                source_audio_codec = audio_streams[0].get('codec_name', '').lower() if audio_streams else ''
                if source_audio_codec == 'aac':
                    logger.info("Source audio is AAC, attempting fallback with -c:a copy")
                    return _try_audio_copy_fallback(source_file, final_output, ffmpeg_path, output_format, output_ext, source_size, progress_callback)
                else:
                    logger.warning(f"Source audio codec is {source_audio_codec}, cannot use copy fallback")
            
            return False, error_msg
        
        # Verify output file was created and has content
        # #region agent log
        _debug_log("H3", "transcoder.py:293", "Verifying output file", {"final_output": str(final_output), "exists": final_output.exists()})
        # #endregion
        
        if not final_output.exists():
            # #region agent log
            _debug_log("H3", "transcoder.py:295", "Output file does not exist", {"final_output": str(final_output)})
            # #endregion
            return False, "Output file was not created - FFmpeg may have failed silently"
        
        try:
            output_size = final_output.stat().st_size
            # #region agent log
            _debug_log("H3", "transcoder.py:298", "Output file size check", {"output_size": output_size, "source_size": source_size})
            # #endregion
            
            if output_size == 0:
                final_output.unlink()
                # #region agent log
                _debug_log("H3", "transcoder.py:300", "Output file is empty", {"final_output": str(final_output)})
                # #endregion
                return False, "Output file is empty - conversion may have failed"
            
            # Verify output is reasonable size (at least 1% of source, or minimum 1MB)
            min_size = max(source_size // 100, 1024 * 1024)  # 1% of source or 1MB
            if output_size < min_size:
                logger.warning(f"Output file seems unusually small: {output_size} bytes (source: {source_size} bytes)")
                # #region agent log
                _debug_log("H3", "transcoder.py:305", "Output file too small", {"output_size": output_size, "min_size": min_size, "source_size": source_size})
                # #endregion
        except OSError as e:
            # #region agent log
            _debug_log("H3", "transcoder.py:307", "OSError verifying output", {"error": str(e), "final_output": str(final_output)})
            # #endregion
            return False, f"Cannot verify output file: {e}"
        
        # If source extension matches output extension, replace original with converted file
        if temp_output is not None:
            logger.info(f"Replacing original {output_format} file: {source_file}")
            # #region agent log
            _debug_log("H2", "transcoder.py:311", f"Replacing original {output_format}", {"source_file": str(source_file), "temp_output": str(temp_output), "final_output": str(final_output), "source_exists": source_file.exists(), "final_exists": final_output.exists()})
            # #endregion
            try:
                # Use shutil.move instead of rename for better cross-platform support
                # First, try to delete the original file (may fail if file is locked)
                import time
                max_retries = 3
                retry_delay = 1.0
                
                for attempt in range(max_retries):
                    try:
                        if source_file.exists():
                            # #region agent log
                            _debug_log("H2", "transcoder.py:315", f"Attempting to unlink source file (attempt {attempt+1}/{max_retries})", {"source_file": str(source_file)})
                            # #endregion
                            source_file.unlink()
                            break
                        else:
                            # Source file doesn't exist, which is fine (maybe already deleted)
                            logger.info(f"Source file does not exist, proceeding with move: {source_file}")
                            break
                    except (OSError, PermissionError) as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Failed to delete source file (attempt {attempt+1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                        else:
                            # Last attempt failed - try shutil.move anyway (it may overwrite on Windows)
                            logger.warning(f"Failed to delete source file after {max_retries} attempts: {e}. Attempting move (may overwrite)...")
                
                # Verify final_output exists before attempting move
                if not final_output.exists():
                    error_msg = f"Converted file does not exist: {final_output}"
                    logger.error(error_msg)
                    # #region agent log
                    _debug_log("H2", "transcoder.py:318", "Final output file does not exist", {"final_output": str(final_output), "source_file": str(source_file)})
                    # #endregion
                    return False, error_msg
                
                # Use shutil.move instead of rename - works better on Windows and can overwrite
                # #region agent log
                _debug_log("H2", "transcoder.py:318", "Moving temp file to original location", {"from": str(final_output), "to": str(source_file), "final_exists": final_output.exists(), "source_exists": source_file.exists()})
                # #endregion
                
                # Retry logic for the move operation
                move_success = False
                for move_attempt in range(max_retries):
                    try:
                        if not final_output.exists():
                            error_msg = f"Converted file disappeared before move (attempt {move_attempt + 1}/{max_retries}): {final_output}"
                            logger.error(error_msg)
                            if move_attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            else:
                                return False, error_msg
                        
                        shutil.move(str(final_output), str(source_file))
                        move_success = True
                        break
                    except (OSError, PermissionError, FileNotFoundError) as move_error:
                        if move_attempt < max_retries - 1:
                            logger.warning(f"Move failed (attempt {move_attempt + 1}/{max_retries}): {move_error}. Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            # Re-check file existence
                            if not final_output.exists():
                                error_msg = f"Converted file disappeared during retry: {final_output}"
                                logger.error(error_msg)
                                return False, error_msg
                        else:
                            raise  # Re-raise on last attempt
                
                if not move_success:
                    error_msg = f"Failed to move file after {max_retries} attempts"
                    logger.error(error_msg)
                    return False, error_msg
                logger.info(f"Conversion complete: {source_file} ({output_format})")
                # Cache the converted file, including subtitle file info if extracted
                subtitle_file = extracted_srt_files[0] if extracted_srt_files else None
                cache_success = cache.cache_file_converted(source_file, original_path=source_file, subtitle_file=subtitle_file)
                if cache_success:
                    logger.info(f"Converted file cached: {source_file}")
                else:
                    logger.warning(f"Failed to cache converted file: {source_file}")
                # #region agent log
                _debug_log("H2", "transcoder.py:319", "File replacement successful", {"source_file": str(source_file)})
                # #endregion
            except (OSError, PermissionError) as e:
                error_msg = f"Failed to replace original file: {e}"
                logger.error(error_msg)
                logger.error(f"Original file: {source_file} (exists: {source_file.exists()})")
                logger.error(f"Temp file: {final_output} (exists: {final_output.exists()})")
                # #region agent log
                _debug_log("H2", "transcoder.py:321", "File replacement failed", {"error": str(e), "error_type": type(e).__name__, "source_file": str(source_file), "final_output": str(final_output), "source_exists": source_file.exists(), "temp_exists": final_output.exists()})
                # #endregion
                # Try to keep the temp file for manual recovery, but also try to clean it up if we can
                logger.warning(f"Temporary converted file kept at: {final_output}")
                logger.warning("File replacement failed - original file may be locked by another process (media player, explorer, etc.)")
                logger.warning(f"Original file location: {source_file}")
                logger.warning(f"Converted file location: {final_output}")
                return False, error_msg
        else:
            # Output will have different extension (e.g., MKV → MP4)
            # Remove original file
            logger.info(f"Removing original file: {source_file}")
            source_file.unlink()
            # Output file is already correctly named (e.g., Show_S01E01_Title.mp4)
            logger.info(f"Conversion complete: {final_output} ({output_format}, preserved original filename)")
            # Cache the converted file, including subtitle file info if extracted
            subtitle_file = extracted_srt_files[0] if extracted_srt_files else None
            cache_success = cache.cache_file_converted(final_output, original_path=source_file, subtitle_file=subtitle_file)
            if cache_success:
                logger.info(f"Converted file cached: {final_output}")
            else:
                logger.warning(f"Failed to cache converted file: {final_output}")
        
        # #region agent log
        _debug_log("ALL", "transcoder.py:332", "Conversion successful", {"source_file": str(source_file), "final_output": str(final_output)})
        # #endregion
        return True, None
    
    except subprocess.TimeoutExpired:
        error_msg = "FFmpeg conversion timed out (exceeded 1 hour)"
        logger.error(error_msg)
        # #region agent log
        _debug_log("ALL", "transcoder.py:347", "Conversion timeout", {"source_file": str(source_file)})
        # #endregion
        
        # Clean up
        if final_output and final_output.exists():
            final_output.unlink()
        
        return False, error_msg
    
    except Exception as e:
        error_msg = f"Unexpected error during conversion: {e}"
        logger.error(error_msg)
        # #region agent log
        _debug_log("ALL", "transcoder.py:357", "Unexpected exception", {"error": str(e), "error_type": type(e).__name__, "source_file": str(source_file)})
        # #endregion
        
        # Clean up
        if final_output and final_output.exists():
            final_output.unlink()
        
        return False, error_msg


def convert_file(file_path: str, create_backup_first: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Convenience wrapper to convert a file from string path.
    Returns (success, error_message).
    """
    return convert_to_mp4_aac(Path(file_path), create_backup_first)


def batch_convert(file_paths: list, create_backup_first: bool = True) -> dict:
    """
    Convert multiple files.
    Returns dict with 'success', 'failed', and 'errors' keys.
    """
    results = {
        'success': [],
        'failed': [],
        'errors': {}
    }
    
    for file_path in file_paths:
        path = Path(file_path)
        
        # Verify file exists before attempting conversion
        if not path.exists():
            error_msg = f"File no longer exists: {file_path}"
            logger.warning(error_msg)
            results['failed'].append(str(path))
            results['errors'][str(path)] = error_msg
            continue
        
        try:
            success, error = convert_to_mp4_aac(path, create_backup_first)
            
            if success:
                results['success'].append(str(path))
                logger.info(f"Successfully converted: {path}")
            else:
                error_msg = error or "Unknown error occurred"
                results['failed'].append(str(path))
                results['errors'][str(path)] = error_msg
                logger.error(f"Failed to convert {path}: {error_msg}")
        
        except Exception as e:
            # Catch any exceptions to ensure batch continues
            error_msg = f"Exception during conversion: {e}"
            results['failed'].append(str(path))
            results['errors'][str(path)] = error_msg
            logger.error(f"Exception converting {path}: {e}", exc_info=True)
            # Continue with next file
    
    return results
