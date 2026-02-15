"""
UNC Path Authentication Module for Jellyfin Audio Service.
Handles authentication to UNC paths using Windows Credential Manager.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Set

logger = logging.getLogger(__name__)
# Debug log path (relative to this file so it works from any install path)
_DEBUG_LOG_PATH = Path(__file__).resolve().parent / ".cursor" / "debug.log"

# Track authenticated UNC shares to avoid re-authenticating
_authenticated_shares: Set[str] = set()

try:
    import win32net
    import win32netcon
    WIN32_NET_AVAILABLE = True
except ImportError:
    WIN32_NET_AVAILABLE = False
    logger.warning("win32net not available - UNC authentication will use net use command. Install pywin32: pip install pywin32")

try:
    import win32cred
    import pywintypes
    WIN32_CRED_AVAILABLE = True
except ImportError:
    WIN32_CRED_AVAILABLE = False
    logger.warning("win32cred not available - credential storage disabled. Install pywin32: pip install pywin32")


def is_unc_path(path: str) -> bool:
    """Check if a path is a UNC path (starts with \\)."""
    return path.startswith('\\\\') or path.startswith('//')


def get_unc_server_share(path: str) -> Optional[Tuple[str, str]]:
    """
    Extract server and share from UNC path.
    Returns (server, share) tuple or None if not a valid UNC path.
    Example: \\\\server\\share\\folder -> ('server', 'share')
    """
    if not is_unc_path(path):
        return None
    
    # Normalize path separators
    normalized = path.replace('/', '\\')
    
    # Remove leading backslashes
    parts = normalized.lstrip('\\').split('\\')
    
    if len(parts) >= 2:
        return (parts[0], parts[1])
    elif len(parts) == 1:
        # Just server, no share
        return (parts[0], None)
    
    return None


def test_unc_access(path: str, username: Optional[str] = None, password: Optional[str] = None) -> Tuple[bool, str]:
    """
    Test access to a path (UNC or local).
    Uses simple file operations like the subtitle program - no authentication required.
    Returns (success, error_message) tuple.
    """
    # #region agent log
    import json
    import time as time_module
    log_entry = {
        "sessionId": "debug-session",
        "runId": "unc-test-v2",
        "hypothesisId": "H1,H2,H3,H4",
        "location": "unc_auth.py:test_unc_access",
        "message": "test_unc_access entry",
        "data": {"path": path, "path_repr": repr(path), "path_type": type(path).__name__},
        "timestamp": int(time_module.time() * 1000)
    }
    try:
        with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except: pass
    # #endregion
    
    try:
        # #region agent log
        log_entry_before_exists = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "H1",
            "location": "unc_auth.py:test_unc_access",
            "message": "Before os.path.exists check",
            "data": {"path": path},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_before_exists) + '\n')
        except: pass
        # #endregion
        
        # Use simple file operations like the subtitle program
        # Check if path exists
        exists_result = os.path.exists(path)
        
        # #region agent log
        log_entry_after_exists = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "H1",
            "location": "unc_auth.py:test_unc_access",
            "message": "After os.path.exists check",
            "data": {"path": path, "exists_result": exists_result},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_after_exists) + '\n')
        except: pass
        # #endregion
        
        if not exists_result:
            # HYPOTHESIS H2: os.path.exists() may fail for UNC paths, but os.listdir() might work
            # Try alternative approach - attempt to list directory directly
            # #region agent log
            log_entry_try_listdir = {
                "sessionId": "debug-session",
                "runId": "unc-test-v2",
                "hypothesisId": "H2",
                "location": "unc_auth.py:test_unc_access",
                "message": "os.path.exists returned False, trying os.listdir anyway",
                "data": {"path": path},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_try_listdir) + '\n')
            except: pass
            # #endregion
            
            try:
                # Try to list directory - this might work even if exists() returns False
                dir_contents = list(os.listdir(path))
                # #region agent log
                log_entry_listdir_success = {
                    "sessionId": "debug-session",
                    "runId": "unc-test-v2",
                    "hypothesisId": "H2",
                    "location": "unc_auth.py:test_unc_access",
                    "message": "H2 CONFIRMED: os.listdir succeeded even though exists() returned False",
                    "data": {"path": path, "item_count": len(dir_contents)},
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_success) + '\n')
                except: pass
                # #endregion
                return (True, "")
            except Exception as listdir_e:
                # #region agent log
                log_entry_listdir_failed = {
                    "sessionId": "debug-session",
                    "runId": "unc-test-v2",
                    "hypothesisId": "H2",
                    "location": "unc_auth.py:test_unc_access",
                    "message": "os.listdir also failed",
                    "data": {"path": path, "error": str(listdir_e), "error_type": type(listdir_e).__name__},
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_failed) + '\n')
                except: pass
                # #endregion
                return (False, f"Path does not exist: {path}")
        
        # #region agent log
        log_entry_before_access = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "H3",
            "location": "unc_auth.py:test_unc_access",
            "message": "Before os.access check",
            "data": {"path": path},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_before_access) + '\n')
        except: pass
        # #endregion
        
        # Check if path is accessible (readable)
        access_result = os.access(path, os.R_OK)
        
        # #region agent log
        log_entry_after_access = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "H3",
            "location": "unc_auth.py:test_unc_access",
            "message": "After os.access check",
            "data": {"path": path, "access_result": access_result},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_after_access) + '\n')
        except: pass
        # #endregion
        
        if not access_result:
            return (False, f"Path is not accessible (no read permission): {path}")
        
        # Try to list directory contents to verify we can actually read it
        if os.path.isdir(path):
            # #region agent log
            log_entry_before_listdir = {
                "sessionId": "debug-session",
                "runId": "unc-test-v2",
                "hypothesisId": "H4",
                "location": "unc_auth.py:test_unc_access",
                "message": "Before os.listdir (directory check)",
                "data": {"path": path},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry_before_listdir) + '\n')
            except: pass
            # #endregion
            
            try:
                dir_contents = list(os.listdir(path))
                # #region agent log
                log_entry_listdir_success2 = {
                    "sessionId": "debug-session",
                    "runId": "unc-test-v2",
                    "hypothesisId": "H4",
                    "location": "unc_auth.py:test_unc_access",
                    "message": "os.listdir succeeded",
                    "data": {"path": path, "item_count": len(dir_contents)},
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_success2) + '\n')
                except: pass
                # #endregion
            except PermissionError as pe:
                # #region agent log
                log_entry_permission = {
                    "sessionId": "debug-session",
                    "runId": "unc-test-v2",
                    "hypothesisId": "H4",
                    "location": "unc_auth.py:test_unc_access",
                    "message": "PermissionError on listdir",
                    "data": {"path": path, "error": str(pe)},
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_permission) + '\n')
                except: pass
                # #endregion
                return (False, f"Permission denied accessing path: {path}")
            except Exception as e:
                # #region agent log
                log_entry_listdir_error = {
                    "sessionId": "debug-session",
                    "runId": "unc-test-v2",
                    "hypothesisId": "H4",
                    "location": "unc_auth.py:test_unc_access",
                    "message": "Exception on listdir",
                    "data": {"path": path, "error": str(e), "error_type": type(e).__name__},
                    "timestamp": int(time_module.time() * 1000)
                }
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry_listdir_error) + '\n')
                except: pass
                # #endregion
                return (False, f"Error accessing path: {str(e)}")
        elif os.path.isfile(path):
            # For files, just verify we can access it
            try:
                with open(path, 'rb'):
                    pass
            except PermissionError:
                return (False, f"Permission denied accessing path: {path}")
            except Exception as e:
                return (False, f"Error accessing path: {str(e)}")
        
        # #region agent log
        log_entry_success = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "ALL",
            "location": "unc_auth.py:test_unc_access",
            "message": "Path test successful",
            "data": {"path": path},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_success) + '\n')
        except: pass
        # #endregion
        
        return (True, "")
    
    except Exception as e:
        # #region agent log
        log_entry_exception = {
            "sessionId": "debug-session",
            "runId": "unc-test-v2",
            "hypothesisId": "H5",
            "location": "unc_auth.py:test_unc_access",
            "message": "Exception in test_unc_access",
            "data": {"path": path, "error": str(e), "error_type": type(e).__name__},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry_exception) + '\n')
        except: pass
        # #endregion
        logger.error(f"Error testing path access for {path}: {e}")
        return (False, f"Error testing path access: {str(e)}")


def _test_unc_with_credentials(server: str, share: Optional[str], username: str, password: str) -> Tuple[bool, str]:
    """Test UNC access with provided credentials using net use command."""
    try:
        # Build UNC path
        if share:
            unc_path = f"\\\\{server}\\{share}"
        else:
            unc_path = f"\\\\{server}"
        
        # Use net use to test connection
        # We'll use a temporary connection that we'll disconnect
        # Format: net use \\server\share /user:username password
        # Note: Password must be passed as a separate argument after /user
        # #region agent log
        import json
        import time as time_module
        log_entry = {
            "sessionId": "debug-session",
            "runId": "unc-auth-test",
            "hypothesisId": "H1",
            "location": "unc_auth.py:_test_unc_with_credentials",
            "message": "Testing UNC credentials",
            "data": {"server": server, "share": share, "unc_path": unc_path, "username": username, "has_password": bool(password)},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except: pass
        # #endregion
        
        # Use net use command - password as separate argument after /user
        cmd = [
            'net', 'use', unc_path,
            f'/user:{username}',
            password
        ]
        
        # #region agent log
        log_entry2 = {
            "sessionId": "debug-session",
            "runId": "unc-auth-test",
            "hypothesisId": "H2",
            "location": "unc_auth.py:_test_unc_with_credentials",
            "message": "Executing net use command",
            "data": {"cmd": ' '.join(['net', 'use', unc_path, f'/user:{username}', '***']), "unc_path": unc_path},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry2) + '\n')
        except: pass
        # #endregion
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        # #region agent log
        log_entry3 = {
            "sessionId": "debug-session",
            "runId": "unc-auth-test",
            "hypothesisId": "H3",
            "location": "unc_auth.py:_test_unc_with_credentials",
            "message": "net use result",
            "data": {"returncode": result.returncode, "stdout": result.stdout[:200], "stderr": result.stderr[:200] if result.stderr else None},
            "timestamp": int(time_module.time() * 1000)
        }
        try:
            with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry3) + '\n')
        except: pass
        # #endregion
        
        if result.returncode == 0:
            # Successfully connected, now disconnect
            subprocess.run(
                ['net', 'use', unc_path, '/delete', '/y'],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # #region agent log
            log_entry4 = {
                "sessionId": "debug-session",
                "runId": "unc-auth-test",
                "hypothesisId": "H4",
                "location": "unc_auth.py:_test_unc_with_credentials",
                "message": "Authentication successful",
                "data": {"unc_path": unc_path},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry4) + '\n')
            except: pass
            # #endregion
            return (True, "")
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            # #region agent log
            log_entry5 = {
                "sessionId": "debug-session",
                "runId": "unc-auth-test",
                "hypothesisId": "H5",
                "location": "unc_auth.py:_test_unc_with_credentials",
                "message": "Authentication failed",
                "data": {"unc_path": unc_path, "error": error_msg[:200]},
                "timestamp": int(time_module.time() * 1000)
            }
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry5) + '\n')
            except: pass
            # #endregion
            return (False, f"Authentication failed: {error_msg.strip()}")
    
    except subprocess.TimeoutExpired:
        return (False, "Connection timeout")
    except Exception as e:
        return (False, f"Error testing credentials: {str(e)}")


def store_unc_credentials(unc_path: str, username: str, password: str) -> bool:
    """
    Store credentials for a UNC path in Windows Credential Manager.
    Returns True if successful, False otherwise.
    """
    if not WIN32_CRED_AVAILABLE:
        logger.warning("win32cred not available - cannot store credentials")
        return False
    
    if not is_unc_path(unc_path):
        logger.warning(f"Not a UNC path, skipping credential storage: {unc_path}")
        return False
    
    try:
        server_share = get_unc_server_share(unc_path)
        if not server_share:
            logger.error(f"Invalid UNC path format: {unc_path}")
            return False
        
        server, share = server_share
        
        # Create credential target name
        # Format: WindowsCredential:server:share or WindowsCredential:server
        if share:
            target_name = f"WindowsCredential:{server}:{share}"
        else:
            target_name = f"WindowsCredential:{server}"
        
        # Store in Windows Credential Manager
        # Use CRED_TYPE_GENERIC for network credentials
        credential = {
            'Type': win32cred.CRED_TYPE_GENERIC,
            'TargetName': target_name,
            'UserName': username,
            'CredentialBlob': password,
            'Comment': f'Jellyfin Audio Service credentials for {unc_path}',
            'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE  # Persist across reboots
        }
        
        win32cred.CredWrite(credential, 0)
        logger.info(f"Stored credentials for UNC path: {unc_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error storing credentials for {unc_path}: {e}")
        return False


def get_unc_credentials(unc_path: str) -> Optional[Tuple[str, str]]:
    """
    Retrieve credentials for a UNC path from Windows Credential Manager.
    Returns (username, password) tuple or None if not found.
    """
    if not WIN32_CRED_AVAILABLE:
        return None
    
    if not is_unc_path(unc_path):
        return None
    
    try:
        server_share = get_unc_server_share(unc_path)
        if not server_share:
            return None
        
        server, share = server_share
        
        # Try to find credentials
        if share:
            target_name = f"WindowsCredential:{server}:{share}"
        else:
            target_name = f"WindowsCredential:{server}"
        
        try:
            credential = win32cred.CredRead(target_name, win32cred.CRED_TYPE_GENERIC, 0)
            username = credential['UserName']
            password = credential['CredentialBlob'].decode('utf-16le') if isinstance(credential['CredentialBlob'], bytes) else str(credential['CredentialBlob'])
            return (username, password)
        except pywintypes.error as e:
            if e.winerror == win32cred.ERROR_NOT_FOUND:
                # No credentials stored
                return None
            raise
    
    except Exception as e:
        logger.error(f"Error retrieving credentials for {unc_path}: {e}")
        return None


def delete_unc_credentials(unc_path: str) -> bool:
    """
    Delete stored credentials for a UNC path.
    Returns True if successful, False otherwise.
    """
    if not WIN32_CRED_AVAILABLE:
        return False
    
    if not is_unc_path(unc_path):
        return False
    
    try:
        server_share = get_unc_server_share(unc_path)
        if not server_share:
            return False
        
        server, share = server_share
        
        if share:
            target_name = f"WindowsCredential:{server}:{share}"
        else:
            target_name = f"WindowsCredential:{server}"
        
        try:
            win32cred.CredDelete(target_name, win32cred.CRED_TYPE_GENERIC, 0)
            logger.info(f"Deleted credentials for UNC path: {unc_path}")
            return True
        except pywintypes.error as e:
            if e.winerror == win32cred.ERROR_NOT_FOUND:
                # Credentials don't exist, that's fine
                return True
            logger.error(f"Error deleting credentials: {e}")
            return False
    
    except Exception as e:
        logger.error(f"Error deleting credentials for {unc_path}: {e}")
        return False


def get_unc_share_root(unc_path: str) -> Optional[str]:
    """
    Extract the UNC share root from a full path.
    Example: \\\\server\\share\\folder\\file.mkv -> \\\\server\\share
    """
    if not is_unc_path(unc_path):
        return None
    
    # Remove leading \\ and split
    parts = unc_path[2:].split('\\', 2)
    if len(parts) >= 2:
        return f"\\\\{parts[0]}\\{parts[1]}"
    return None


def authenticate_unc_path(unc_path: str, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """
    Authenticate to a UNC network share using provided credentials.
    Uses win32net.NetUseAdd if available, otherwise falls back to net use command.
    
    Args:
        unc_path: Full UNC path (e.g., \\\\server\\share\\folder\\file.mkv)
        username: Username for authentication (e.g., "DOMAIN\\username" or "username")
        password: Password for authentication
        
    Returns:
        True if authentication successful or already authenticated, False otherwise
    """
    if not is_unc_path(unc_path):
        # Not a UNC path, no authentication needed
        return True
    
    # Get the share root (e.g., \\server\share)
    share_root = get_unc_share_root(unc_path)
    if not share_root:
        logger.warning(f"Could not extract share root from UNC path: {unc_path}")
        return False
    
    # Check if already authenticated
    if share_root in _authenticated_shares:
        logger.debug(f"UNC share {share_root} already authenticated")
        return True
    
    # If no credentials provided, try to access without explicit auth
    # (will use current user's credentials or cached credentials)
    if not username or not password:
        try:
            # #region agent log
            ex_unc = os.path.exists(unc_path)
            ex_sh = os.path.exists(share_root)
            log_entry = {"sessionId": "debug-session", "runId": "unc-enauth", "hypothesisId": "H1,H4", "location": "unc_auth.py:authenticate_unc_path", "message": "No-creds: exists check", "data": {"unc_path": unc_path, "share_root": share_root, "exists_unc_path": ex_unc, "exists_share_root": ex_sh}, "timestamp": int(__import__('time').time() * 1000)}
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(__import__('json').dumps(log_entry) + '\n')
            except: pass
            # #endregion
            # Try to access the path - if it works, credentials are already cached
            if ex_unc or ex_sh:
                logger.info(f"UNC path {share_root} accessible without explicit authentication")
                _authenticated_shares.add(share_root)
                return True
            # H3: when both exists are False, try listdir(share_root) to see if it would work
            # #region agent log
            listdir_ok = False
            listdir_err = None
            try:
                list(os.listdir(share_root))
                listdir_ok = True
            except Exception as le:
                listdir_err = str(le)
            log_entry2 = {"sessionId": "debug-session", "runId": "unc-enauth", "hypothesisId": "H3", "location": "unc_auth.py:authenticate_unc_path", "message": "No-creds: listdir(share_root) when exists=False", "data": {"share_root": share_root, "listdir_ok": listdir_ok, "error": listdir_err}, "timestamp": int(__import__('time').time() * 1000)}
            try:
                with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                    f.write(__import__('json').dumps(log_entry2) + '\n')
            except: pass
            # #endregion
        except Exception:
            pass
        
        logger.warning(f"No credentials provided for UNC path {share_root} and path is not accessible")
        return False
    
    try:
        if WIN32_NET_AVAILABLE:
            # Use win32net.NetUseAdd (preferred method - more reliable)
            # Parse username (handle DOMAIN\username format)
            if '\\' in username:
                domain, user = username.split('\\', 1)
            else:
                domain = None
                user = username
            
            use_info = {
                'remote': share_root,
                'password': password,
                'username': user,
                'domainname': domain or '',
            }
            
            logger.info(f"Authenticating to UNC share {share_root} as {username}")
            
            try:
                # Try to add the network connection
                win32net.NetUseAdd(None, 2, use_info)
                logger.info(f"Successfully authenticated to UNC share {share_root}")
                _authenticated_shares.add(share_root)
                return True
            except Exception as e:
                error_code = getattr(e, 'winerror', None) or getattr(e, 'args', [None])[0]
                
                # Error 1219: Multiple connections to a server or shared resource
                # This means we're already connected, which is fine
                if error_code == 1219:
                    logger.info(f"Already connected to UNC share {share_root}")
                    _authenticated_shares.add(share_root)
                    return True
                
                logger.error(f"Failed to authenticate to UNC share {share_root}: {e} (error code: {error_code})")
                return False
        else:
            # Fallback to net use command
            server_share = get_unc_server_share(share_root)
            if server_share:
                server, share = server_share
                success, error = _test_unc_with_credentials(server, share, username, password)
                if success:
                    _authenticated_shares.add(share_root)
                return success
            
    except Exception as e:
        logger.error(f"Error authenticating to UNC path {unc_path}: {e}", exc_info=True)
        return False
    
    return False


def ensure_unc_access(path: str, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """
    Ensure we have access to a UNC path, authenticating if necessary.
    This should be called before accessing any UNC path.
    
    Args:
        path: Path to check/authenticate (can be UNC or local)
        username: Optional username for UNC authentication
        password: Optional password for UNC authentication
        
    Returns:
        True if path is accessible, False otherwise
    """
    if not is_unc_path(path):
        # Local path, no authentication needed
        return True
    
    # Authenticate to the UNC share
    if authenticate_unc_path(path, username, password):
        # Verify we can actually access it
        try:
            share_root = get_unc_share_root(path)
            if share_root:
                # #region agent log
                ex_sh = os.path.exists(share_root)
                ex_path = os.path.exists(path)
                log_ev = {"sessionId": "debug-session", "runId": "unc-enauth", "hypothesisId": "H2,H5", "location": "unc_auth.py:ensure_unc_access", "message": "Verify: exists check", "data": {"path": path, "share_root": share_root, "exists_share_root": ex_sh, "exists_path": ex_path}, "timestamp": int(__import__('time').time() * 1000)}
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(__import__('json').dumps(log_ev) + '\n')
                except: pass
                # #endregion
                if ex_sh or ex_path:
                    return True
                # H3: try listdir when exists is False
                # #region agent log
                ld_sh, ld_path = False, False
                try: list(os.listdir(share_root)); ld_sh = True
                except Exception: pass
                try: list(os.listdir(path)); ld_path = True
                except Exception: pass
                log_ev2 = {"sessionId": "debug-session", "runId": "unc-enauth", "hypothesisId": "H3", "location": "unc_auth.py:ensure_unc_access", "message": "Verify: listdir when exists=False", "data": {"path": path, "share_root": share_root, "listdir_share_ok": ld_sh, "listdir_path_ok": ld_path}, "timestamp": int(__import__('time').time() * 1000)}
                try:
                    with open(str(_DEBUG_LOG_PATH), 'a', encoding='utf-8') as f:
                        f.write(__import__('json').dumps(log_ev2) + '\n')
                except: pass
                # #endregion
        except Exception as e:
            logger.warning(f"Could not verify access to {path} after authentication: {e}")
    
    return False


def authenticate_unc_path_legacy(unc_path: str) -> Tuple[bool, str]:
    """
    Authenticate to a UNC path using stored credentials (legacy method).
    Returns (success, error_message) tuple.
    """
    if not WIN32_CRED_AVAILABLE:
        return (False, "win32cred not available")
    
    if not is_unc_path(unc_path):
        # Local path - no authentication needed
        return (True, "")
    
    # Try to get stored credentials
    credentials = get_unc_credentials(unc_path)
    
    if not credentials:
        return (False, "No credentials stored for this UNC path")
    
    username, password = credentials
    
    # Test access with credentials
    return test_unc_access(unc_path, username, password)

