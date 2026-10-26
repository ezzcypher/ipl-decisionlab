"""Per-session native theme for the in-app dark/light toggle.

Streamlit builds each session's theme from the process-wide config when a script run starts. Setting the
config from inside the script therefore lags one run and leaks between concurrent users. This wraps the
(internal) new-session message builder so it applies *this session's* choice, under a lock, right before
the theme is serialized. Tested on streamlit==1.66.1 (pinned in requirements.txt). If Streamlit changes the
internal API, `install()` returns False and the app still themes its own components and charts.
"""
import threading

from core.theme import tokens

_LOCK = threading.Lock()
_FLAG = "_dl_theme_patch"


def native_options(mode):
    t = tokens(mode)
    return {"base": mode, "primaryColor": t["accent"], "backgroundColor": t["bg"],
            "secondaryBackgroundColor": t["surface2"], "textColor": t["text"]}


def install():
    try:
        from streamlit import config
        from streamlit.runtime.app_session import AppSession
    except Exception:  # noqa: BLE001
        return False
    orig = getattr(AppSession, "_create_new_session_message", None)
    if orig is None:
        return False
    if getattr(orig, _FLAG, False):
        return True

    def patched(self, *args, **kwargs):
        try:
            ss = self._session_state
            mode = ss["theme"] if "theme" in ss else "dark"
        except Exception:  # noqa: BLE001
            mode = "dark"
        with _LOCK:
            for k, v in native_options(mode if mode in ("dark", "light") else "dark").items():
                config.set_option(f"theme.{k}", v)
            return orig(self, *args, **kwargs)

    setattr(patched, _FLAG, True)
    AppSession._create_new_session_message = patched
    return True
