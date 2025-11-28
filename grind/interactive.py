"""Non-blocking keyboard listener for interactive mode.

Provides a way to signal "I want to interject" without blocking the grind loop.
Press 'i' during execution to trigger a checkpoint at the next iteration boundary.
"""

import atexit
import select
import sys
import termios
import threading
import tty
from dataclasses import dataclass, field

from grind.models import CheckpointAction
from grind.utils import Color


@dataclass
class InterjectState:
    """Shared state for interject signaling between threads."""

    requested: bool = False
    listener_active: bool = False
    original_settings: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def request_interject(self) -> None:
        with self.lock:
            self.requested = True

    def clear_interject(self) -> None:
        with self.lock:
            self.requested = False

    def is_interject_requested(self) -> bool:
        with self.lock:
            return self.requested


# Global state for the keyboard listener
_interject_state = InterjectState()
_listener_thread: threading.Thread | None = None


def _keyboard_listener() -> None:
    """Background thread that listens for 'i' keypress."""
    global _interject_state

    if not sys.stdin.isatty():
        return

    try:
        while _interject_state.listener_active:
            # Check if input is available (non-blocking)
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                char = sys.stdin.read(1)
                if char.lower() == "i":
                    _interject_state.request_interject()
                    msg = "\n[Interject requested - pausing after current iteration]"
                    print(Color.warning(msg))
    except Exception:
        pass  # Silently handle any terminal issues


def _restore_terminal() -> None:
    """Restore terminal settings on exit."""
    global _interject_state
    if _interject_state.original_settings and sys.stdin.isatty():
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _interject_state.original_settings)
        except Exception:
            pass


def start_keyboard_listener() -> None:
    """Start the background keyboard listener for interject signals."""
    global _listener_thread, _interject_state

    if not sys.stdin.isatty():
        return

    if _interject_state.listener_active:
        return  # Already running

    try:
        # Save original terminal settings
        _interject_state.original_settings = termios.tcgetattr(sys.stdin)
        atexit.register(_restore_terminal)

        # Set terminal to raw mode (character-by-character input)
        tty.setcbreak(sys.stdin.fileno())

        _interject_state.listener_active = True
        _interject_state.clear_interject()

        _listener_thread = threading.Thread(target=_keyboard_listener, daemon=True)
        _listener_thread.start()
    except Exception:
        # If we can't set up the listener, just continue without it
        _interject_state.listener_active = False


def stop_keyboard_listener() -> None:
    """Stop the keyboard listener and restore terminal."""
    global _listener_thread, _interject_state

    _interject_state.listener_active = False

    if _listener_thread is not None:
        _listener_thread.join(timeout=0.5)
        _listener_thread = None

    _restore_terminal()


def is_interject_requested() -> bool:
    """Check if an interject has been requested."""
    return _interject_state.is_interject_requested()


def clear_interject() -> None:
    """Clear the interject request flag."""
    _interject_state.clear_interject()


def show_interject_hint() -> None:
    """Show a hint about how to interject."""
    if sys.stdin.isatty() and _interject_state.listener_active:
        print(Color.dim("  [Press 'i' to interject]"))


def show_checkpoint_menu() -> None:
    """Display the checkpoint menu options."""
    print()
    print(Color.header("=" * 60))
    print(Color.bold("INTERJECT CHECKPOINT"))
    print(Color.header("=" * 60))
    print(Color.info("  [Enter] Continue to next iteration"))
    print(Color.info("  [g]     Inject guidance (one-shot)"))
    print(Color.info("  [p]     Inject persistent guidance"))
    print(Color.info("  [s]     Show status"))
    print(Color.info("  [v]     Run verify command"))
    print(Color.info("  [a]     Abort"))
    print(Color.header("=" * 60))


def get_checkpoint_input() -> tuple[CheckpointAction, str | None]:
    """Get user input at checkpoint.

    Returns:
        Tuple of (action, optional guidance text)
    """
    # Temporarily restore normal terminal mode for input
    if _interject_state.original_settings and sys.stdin.isatty():
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _interject_state.original_settings)
        except Exception:
            pass

    try:
        user_input = input("> ").strip()
    except EOFError:
        return CheckpointAction.CONTINUE, None
    finally:
        # Restore cbreak mode for listener
        if sys.stdin.isatty() and _interject_state.listener_active:
            try:
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                pass

    if not user_input:
        return CheckpointAction.CONTINUE, None

    cmd = user_input.lower()
    if cmd == "a":
        return CheckpointAction.ABORT, None
    elif cmd == "s":
        return CheckpointAction.STATUS, None
    elif cmd == "v":
        return CheckpointAction.RUN_VERIFY, None
    elif cmd == "g":
        # Temporarily restore normal mode for multi-line input
        if _interject_state.original_settings and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _interject_state.original_settings)
            except Exception:
                pass
        print(Color.info("Enter guidance (single line):"))
        try:
            guidance = input("> ").strip()
        except EOFError:
            guidance = ""
        finally:
            if sys.stdin.isatty() and _interject_state.listener_active:
                try:
                    tty.setcbreak(sys.stdin.fileno())
                except Exception:
                    pass
        return CheckpointAction.GUIDANCE, guidance if guidance else None
    elif cmd == "p":
        # Temporarily restore normal mode for multi-line input
        if _interject_state.original_settings and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _interject_state.original_settings)
            except Exception:
                pass
        print(Color.info("Enter persistent guidance (single line):"))
        try:
            guidance = input("> ").strip()
        except EOFError:
            guidance = ""
        finally:
            if sys.stdin.isatty() and _interject_state.listener_active:
                try:
                    tty.setcbreak(sys.stdin.fileno())
                except Exception:
                    pass
        return CheckpointAction.GUIDANCE_PERSIST, guidance if guidance else None
    else:
        # Treat any other input as one-shot guidance
        return CheckpointAction.GUIDANCE, user_input
